from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import smtplib
from email.message import EmailMessage
from typing import Any
from uuid import UUID, uuid4

import httpx
from aio_pika import IncomingMessage
from sqlalchemy import text

from app.config import get_settings
from app.infrastructure.db import SessionLocal

logger = logging.getLogger(__name__)
settings = get_settings()


def _to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {}
    return {}


def _resolve_destinations(destinations: list[dict], policy_json: dict[str, Any], severity: str) -> list[dict]:
    enabled_destinations = [item for item in destinations if bool(item.get("enabled"))]
    if not enabled_destinations:
        return []

    severity_map = policy_json.get("severity_destination_ids")
    if isinstance(severity_map, dict):
        raw_ids = severity_map.get(severity)
        if isinstance(raw_ids, list) and raw_ids:
            wanted = {str(item) for item in raw_ids}
            selected = [item for item in enabled_destinations if str(item.get("destination_id")) in wanted]
            if selected:
                return selected

    default_ids = policy_json.get("default_destination_ids")
    if isinstance(default_ids, list) and default_ids:
        wanted = {str(item) for item in default_ids}
        selected = [item for item in enabled_destinations if str(item.get("destination_id")) in wanted]
        if selected:
            return selected

    return enabled_destinations


async def _send_email(
    *,
    smtp_host: str,
    smtp_port: int,
    smtp_username: str,
    smtp_password: str,
    smtp_tls: bool,
    sender: str,
    recipients: list[str],
    subject: str,
    body: str,
) -> None:
    def _run() -> None:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = sender
        message["To"] = ", ".join(recipients)
        message.set_content(body)
        with smtplib.SMTP(host=smtp_host, port=smtp_port, timeout=10) as smtp:
            if smtp_tls:
                smtp.starttls()
            if smtp_username and smtp_password:
                smtp.login(smtp_username, smtp_password)
            smtp.send_message(message)

    await asyncio.to_thread(_run)


async def _deliver_to_destination(destination: dict, alert_payload: dict[str, Any]) -> tuple[str, int | None, str | None, str | None]:
    channel = str(destination.get("channel") or "")
    config = _to_dict(destination.get("config_json"))

    if channel == "webhook":
        url = str(config.get("url") or "").strip()
        if not url:
            return "failed", None, None, "Missing webhook URL"
        body_bytes = json.dumps(alert_payload, default=str).encode("utf-8")
        signature = hmac.new(
            settings.alert_router_webhook_signing_secret.encode("utf-8"),
            body_bytes,
            hashlib.sha256,
        ).hexdigest()
        async with httpx.AsyncClient(timeout=settings.alert_router_timeout_seconds) as client:
            response = await client.post(
                url,
                content=body_bytes,
                headers={"Content-Type": "application/json", "X-Aegis-Signature": f"sha256={signature}"},
            )
            if 200 <= response.status_code < 300:
                return "delivered", response.status_code, response.text[:4000], None
            return "failed", response.status_code, response.text[:4000], f"Webhook returned {response.status_code}"

    if channel == "slack":
        url = str(config.get("webhook_url") or "").strip()
        if not url:
            return "failed", None, None, "Missing Slack webhook URL"
        text_payload = {
            "text": f"Aegis alert | severity={alert_payload.get('severity', 'n/a')} | tenant={alert_payload.get('tenant_id', 'n/a')}"
        }
        async with httpx.AsyncClient(timeout=settings.alert_router_timeout_seconds) as client:
            response = await client.post(url, json=text_payload)
            if 200 <= response.status_code < 300:
                return "delivered", response.status_code, response.text[:4000], None
            return "failed", response.status_code, response.text[:4000], f"Slack returned {response.status_code}"

    if channel == "email":
        raw_to = config.get("to")
        if isinstance(raw_to, str):
            recipients = [raw_to]
        elif isinstance(raw_to, list):
            recipients = [str(item).strip() for item in raw_to if str(item).strip()]
        else:
            recipients = []

        if not recipients:
            return "failed", None, None, "Missing recipient email address"

        smtp_host = str(config.get("smtp_host") or settings.alert_router_email_smtp_host)
        smtp_port = int(config.get("smtp_port") or settings.alert_router_email_smtp_port)
        smtp_username = str(config.get("smtp_username") or settings.alert_router_email_smtp_username)
        smtp_password = str(config.get("smtp_password") or settings.alert_router_email_smtp_password)
        smtp_tls = bool(config.get("smtp_tls") if config.get("smtp_tls") is not None else settings.alert_router_email_smtp_tls)
        sender = str(config.get("from") or settings.alert_router_email_from)
        subject = str(config.get("subject") or "Aegis alert notification")
        body = json.dumps(alert_payload, indent=2, default=str)
        try:
            await _send_email(
                smtp_host=smtp_host,
                smtp_port=smtp_port,
                smtp_username=smtp_username,
                smtp_password=smtp_password,
                smtp_tls=smtp_tls,
                sender=sender,
                recipients=recipients,
                subject=subject,
                body=body,
            )
            return "delivered", None, None, None
        except Exception as exc:  # noqa: BLE001
            return "failed", None, None, f"Email delivery failed: {exc}"

    return "failed", None, None, f"Unsupported channel '{channel}'"


class AlertRouter:
    def __init__(self, rabbit_channel):
        self.rabbit_channel = rabbit_channel
        self.queue = None
        self.consumer_tag: str | None = None

    async def start(self) -> None:
        self.queue = await self.rabbit_channel.declare_queue(
            settings.rabbitmq_alerts_routing_queue,
            durable=True,
            arguments={"x-dead-letter-exchange": settings.rabbitmq_dlx_exchange},
        )
        self.consumer_tag = await self.queue.consume(self._on_alert)

    async def stop(self) -> None:
        if self.queue is not None and self.consumer_tag is not None:
            await self.queue.cancel(self.consumer_tag)

    async def _on_alert(self, message: IncomingMessage) -> None:
        try:
            parsed = json.loads(message.body.decode("utf-8"))
            payload = parsed.get("data") if isinstance(parsed, dict) and isinstance(parsed.get("data"), dict) else parsed
            payload = payload if isinstance(payload, dict) else {}

            tenant_id = payload.get("tenant_id")
            if not isinstance(tenant_id, str) or not tenant_id:
                logger.warning("alert_router_missing_tenant", extra={"payload": payload})
                await message.ack()
                return

            severity = str(payload.get("severity") or "high")
            alert_key = str(payload.get("alert_id") or payload.get("event_id") or uuid4())
            event_id_raw = payload.get("event_id")
            event_id = None
            if isinstance(event_id_raw, str):
                try:
                    event_id = UUID(event_id_raw)
                except ValueError:
                    event_id = None

            async with SessionLocal() as session:
                destinations_rows = await session.execute(
                    text(
                        """
                        SELECT destination_id, tenant_id, channel, enabled, config_json
                        FROM control_alert_destinations
                        WHERE tenant_id = :tenant_id
                        """
                    ),
                    {"tenant_id": tenant_id},
                )
                destinations = [dict(row._mapping) for row in destinations_rows]

                policy_row = await session.execute(
                    text(
                        """
                        SELECT policy_json
                        FROM control_alert_routing_policy
                        WHERE tenant_id = :tenant_id
                        LIMIT 1
                        """
                    ),
                    {"tenant_id": tenant_id},
                )
                policy_item = policy_row.first()
                policy = _to_dict(policy_item._mapping.get("policy_json")) if policy_item else {}

                selected_destinations = _resolve_destinations(destinations, policy, severity)

                for destination in selected_destinations:
                    destination_id = UUID(str(destination["destination_id"]))

                    existing_success = await session.execute(
                        text(
                            """
                            SELECT 1
                            FROM control_alert_delivery_logs
                            WHERE tenant_id = :tenant_id
                              AND destination_id = :destination_id
                              AND alert_key = :alert_key
                              AND status = 'delivered'
                            LIMIT 1
                            """
                        ),
                        {
                            "tenant_id": tenant_id,
                            "destination_id": str(destination_id),
                            "alert_key": alert_key,
                        },
                    )
                    if existing_success.first() is not None:
                        continue

                    for attempt in range(1, settings.alert_router_max_attempts + 1):
                        status, response_code, response_body, error_message = await _deliver_to_destination(destination, payload)
                        await session.execute(
                            text(
                                """
                                INSERT INTO control_alert_delivery_logs (
                                    tenant_id,
                                    destination_id,
                                    channel,
                                    alert_key,
                                    event_id,
                                    status,
                                    attempt_no,
                                    response_code,
                                    response_body,
                                    error_message,
                                    payload_json,
                                    is_test,
                                    attempted_at,
                                    delivered_at
                                ) VALUES (
                                    :tenant_id,
                                    :destination_id,
                                    :channel,
                                    :alert_key,
                                    :event_id,
                                    :status,
                                    :attempt_no,
                                    :response_code,
                                    :response_body,
                                    :error_message,
                                    CAST(:payload_json AS jsonb),
                                    FALSE,
                                    NOW(),
                                    CASE WHEN :is_delivered THEN NOW() ELSE NULL END
                                )
                                """
                            ),
                            {
                                "tenant_id": tenant_id,
                                "destination_id": str(destination_id),
                                "channel": destination["channel"],
                                "alert_key": alert_key,
                                "event_id": str(event_id) if event_id else None,
                                "status": status,
                                "attempt_no": attempt,
                                "response_code": response_code,
                                "response_body": response_body,
                                "error_message": error_message,
                                "payload_json": json.dumps(payload, default=str),
                                "is_delivered": status == "delivered",
                            },
                        )
                        await session.commit()

                        if status == "delivered":
                            break
                        if attempt < settings.alert_router_max_attempts:
                            await asyncio.sleep(min(2**attempt, 5))

            await message.ack()
        except Exception as exc:  # noqa: BLE001
            logger.exception("alert_router_consume_failed", extra={"error": str(exc)})
            await message.ack()
