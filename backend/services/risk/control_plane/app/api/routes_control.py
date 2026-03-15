from __future__ import annotations

import asyncio
import csv
import hashlib
import hmac
import io
import json
import logging
import smtplib
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Any
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from risk_common.schemas_v2 import AuthClaims, RiskEventIngestRequest
from risk_common.security import create_access_token
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    enforce_tenant_access,
    is_platform_operator,
    require_any_scope,
    require_scope,
)
from app.api.schemas import (
    AlertDestinationCreateRequest,
    AlertDestinationDTO,
    AlertDestinationUpdateRequest,
    AlertRoutingPolicyDTO,
    AlertRoutingPolicyUpdateRequest,
    AlertRoutingTestRequest,
    ConfigAuditItem,
    ConnectorCatalogItem,
    DeliveryLogItem,
    DeliveryResult,
    ModelActivateRequest,
    ModelPolicyUpdateRequest,
    ReconciliationSummaryDTO,
    TenantAdminAssignRequest,
    TenantConfigurationDTO,
    TenantConfigurationUpdateRequest,
    TenantConnectorPolicyResponse,
    TenantConnectorPolicyUpdateRequest,
    TenantCreateRequest,
    TenantSummary,
    TenantUpdateRequest,
    TestDatasetSummary,
    TestDatasetUploadRequest,
    TestRunCreateRequest,
    TestRunResultItem,
    TestRunSummary,
)
from app.config import get_settings
from app.infrastructure.db import get_db_session
from app.infrastructure.repository import ALLOWED_RULE_KEYS, ControlRepository

router = APIRouter(prefix="/control/v1", tags=["control-plane"])
settings = get_settings()
logger = logging.getLogger(__name__)


def _normalize_rule_overrides(overrides: dict[str, Any]) -> dict[str, float]:
    unknown = [key for key in overrides if key not in ALLOWED_RULE_KEYS]
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unsupported rule override keys: {', '.join(sorted(unknown))}")

    numeric: dict[str, float] = {}
    for key, raw_value in overrides.items():
        if raw_value is None:
            continue
        try:
            value = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=f"Rule override '{key}' must be numeric") from exc

        if key.endswith("_weight") or key.endswith("_threshold"):
            if value < 0:
                raise HTTPException(status_code=422, detail=f"Rule override '{key}' must be >= 0")
        numeric[key] = value

    bounded_keys = {
        "high_amount_weight",
        "sanctions_weight",
        "pep_weight",
        "proxy_ip_weight",
        "bin_mismatch_weight",
        "jurisdiction_threshold",
        "jurisdiction_weight",
        "cross_border_weight",
    }
    for key in bounded_keys:
        if key in numeric and numeric[key] > 1:
            raise HTTPException(status_code=422, detail=f"Rule override '{key}' must be <= 1")

    return numeric


def _resolve_routing_destinations(destinations: list[dict], policy_json: dict[str, Any], severity: str) -> list[dict]:
    enabled_destinations = [item for item in destinations if bool(item.get("enabled"))]
    if not enabled_destinations:
        return []

    severity_map = policy_json.get("severity_destination_ids")
    if isinstance(severity_map, dict):
        raw_ids = severity_map.get(severity)
        if isinstance(raw_ids, list) and raw_ids:
            desired = {str(item) for item in raw_ids}
            selected = [item for item in enabled_destinations if str(item.get("destination_id")) in desired]
            if selected:
                return selected

    default_ids = policy_json.get("default_destination_ids")
    if isinstance(default_ids, list) and default_ids:
        desired = {str(item) for item in default_ids}
        selected = [item for item in enabled_destinations if str(item.get("destination_id")) in desired]
        if selected:
            return selected

    return enabled_destinations


def _sign_payload(secret: str, payload: dict[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


async def _send_email(
    *,
    smtp_host: str,
    smtp_port: int,
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
            smtp.send_message(message)

    await asyncio.to_thread(_run)


async def _deliver_to_destination(
    *,
    destination: dict,
    alert_payload: dict[str, Any],
    is_test: bool,
) -> tuple[str, int | None, str | None, str | None]:
    channel = str(destination.get("channel") or "")
    config = destination.get("config") if isinstance(destination.get("config"), dict) else {}

    if channel == "webhook":
        target_url = str(config.get("url") or "").strip()
        if not target_url:
            return "failed", None, None, "Missing webhook URL"

        headers: dict[str, str] = {"Content-Type": "application/json"}
        secret = str(config.get("signing_secret") or settings.alert_router_webhook_signing_secret)
        headers["X-Aegis-Signature"] = _sign_payload(secret, alert_payload)
        headers["X-Aegis-Mode"] = "test" if is_test else "live"

        async with httpx.AsyncClient(timeout=settings.alert_router_timeout_seconds) as client:
            response = await client.post(target_url, headers=headers, json=alert_payload)
            if 200 <= response.status_code < 300:
                return "delivered", response.status_code, response.text[:4000], None
            return "failed", response.status_code, response.text[:4000], f"Webhook returned {response.status_code}"

    if channel == "slack":
        target_url = str(config.get("webhook_url") or "").strip()
        if not target_url:
            return "failed", None, None, "Missing Slack webhook URL"

        text_body = {
            "text": f"Aegis {'test ' if is_test else ''}alert | severity={alert_payload.get('severity', 'n/a')}"
        }
        async with httpx.AsyncClient(timeout=settings.alert_router_timeout_seconds) as client:
            response = await client.post(target_url, json=text_body)
            if 200 <= response.status_code < 300:
                return "delivered", response.status_code, response.text[:4000], None
            return "failed", response.status_code, response.text[:4000], f"Slack returned {response.status_code}"

    if channel == "email":
        recipients_raw = config.get("to")
        if isinstance(recipients_raw, str):
            recipients = [recipients_raw]
        elif isinstance(recipients_raw, list):
            recipients = [str(item).strip() for item in recipients_raw if str(item).strip()]
        else:
            recipients = []

        if not recipients:
            return "failed", None, None, "Missing recipient email address"

        smtp_host = str(config.get("smtp_host") or settings.alert_router_email_smtp_host)
        smtp_port = int(config.get("smtp_port") or settings.alert_router_email_smtp_port)
        sender = str(config.get("from") or settings.alert_router_email_from)
        subject = str(config.get("subject") or "Aegis alert notification")
        body = json.dumps(alert_payload, indent=2, default=str)
        try:
            await _send_email(
                smtp_host=smtp_host,
                smtp_port=smtp_port,
                sender=sender,
                recipients=recipients,
                subject=subject,
                body=body,
            )
            return "delivered", None, None, None
        except Exception as exc:  # noqa: BLE001
            return "failed", None, None, f"Email delivery failed: {exc}"

    return "failed", None, None, f"Unsupported channel '{channel}'"


def _parse_time_window(
    *,
    from_ts: datetime | None,
    to_ts: datetime | None,
    default_hours: int,
) -> tuple[datetime, datetime]:
    resolved_to = to_ts or datetime.now(tz=UTC)
    resolved_from = from_ts or (resolved_to - timedelta(hours=default_hours))
    if resolved_from.tzinfo is None:
        resolved_from = resolved_from.replace(tzinfo=UTC)
    if resolved_to.tzinfo is None:
        resolved_to = resolved_to.replace(tzinfo=UTC)
    if resolved_from > resolved_to:
        raise HTTPException(status_code=422, detail="from_ts must be before to_ts")
    return resolved_from, resolved_to


@router.get("/tenants", response_model=list[TenantSummary])
async def list_tenants(
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    claims: AuthClaims = Depends(require_scope("control:tenants:read")),
    session: AsyncSession = Depends(get_db_session),
) -> list[TenantSummary]:
    if not is_platform_operator(claims):
        tenant = await ControlRepository.get_tenant(session, claims.tenant_id)
        if not tenant:
            return []
        return [TenantSummary(**tenant)]
    rows = await ControlRepository.list_tenants(session, status=status, limit=limit, offset=offset)
    return [TenantSummary(**row) for row in rows]


@router.post("/tenants", response_model=TenantSummary)
async def create_tenant(
    payload: TenantCreateRequest,
    claims: AuthClaims = Depends(require_scope("control:tenants:write")),
    session: AsyncSession = Depends(get_db_session),
) -> TenantSummary:
    if not is_platform_operator(claims):
        raise HTTPException(status_code=403, detail="Platform operator scope required")
    try:
        created = await ControlRepository.create_tenant(
            session,
            tenant_id=payload.tenant_id,
            display_name=payload.display_name,
            status=payload.status,
            tier=payload.tier,
            metadata_json=payload.metadata_json,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    await ControlRepository.write_config_audit(
        session,
        tenant_id=payload.tenant_id,
        actor=claims.sub,
        action="create",
        resource_type="tenant",
        resource_id=payload.tenant_id,
        before_json={},
        after_json=created,
    )
    return TenantSummary(**created)


@router.get("/tenants/{tenant_id}", response_model=TenantSummary)
async def get_tenant(
    tenant_id: str,
    claims: AuthClaims = Depends(require_scope("control:tenants:read")),
    session: AsyncSession = Depends(get_db_session),
) -> TenantSummary:
    enforce_tenant_access(claims, tenant_id)
    tenant = await ControlRepository.get_tenant(session, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return TenantSummary(**tenant)


@router.patch("/tenants/{tenant_id}", response_model=TenantSummary)
async def update_tenant(
    tenant_id: str,
    payload: TenantUpdateRequest,
    claims: AuthClaims = Depends(require_scope("control:tenants:write")),
    session: AsyncSession = Depends(get_db_session),
) -> TenantSummary:
    if not is_platform_operator(claims):
        raise HTTPException(status_code=403, detail="Platform operator scope required")
    before = await ControlRepository.get_tenant(session, tenant_id)
    if not before:
        raise HTTPException(status_code=404, detail="Tenant not found")

    updated = await ControlRepository.update_tenant(
        session,
        tenant_id=tenant_id,
        display_name=payload.display_name,
        status=payload.status,
        tier=payload.tier,
        metadata_json=payload.metadata_json,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Tenant not found")

    await ControlRepository.write_config_audit(
        session,
        tenant_id=tenant_id,
        actor=claims.sub,
        action="update",
        resource_type="tenant",
        resource_id=tenant_id,
        before_json=before,
        after_json=updated,
    )
    return TenantSummary(**updated)


@router.post("/tenants/{tenant_id}/admins")
async def assign_tenant_admin(
    tenant_id: str,
    payload: TenantAdminAssignRequest,
    claims: AuthClaims = Depends(require_scope("control:tenants:write")),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    if not is_platform_operator(claims):
        raise HTTPException(status_code=403, detail="Platform operator scope required")
    try:
        result = await ControlRepository.assign_tenant_admin(
            session,
            tenant_id=tenant_id,
            username=payload.username,
            role_name=payload.role_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    await ControlRepository.write_config_audit(
        session,
        tenant_id=tenant_id,
        actor=claims.sub,
        action="assign_admin",
        resource_type="tenant_admin",
        resource_id=f"{tenant_id}:{payload.username}",
        before_json={},
        after_json=result,
    )
    return result


@router.get("/tenants/{tenant_id}/configuration", response_model=TenantConfigurationDTO)
async def get_tenant_configuration(
    tenant_id: str,
    claims: AuthClaims = Depends(require_scope("control:config:read")),
    session: AsyncSession = Depends(get_db_session),
) -> TenantConfigurationDTO:
    enforce_tenant_access(claims, tenant_id)
    tenant = await ControlRepository.get_tenant(session, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    config = await ControlRepository.get_tenant_configuration(session, tenant_id)
    return TenantConfigurationDTO(**config)


@router.put("/tenants/{tenant_id}/configuration", response_model=TenantConfigurationDTO)
async def put_tenant_configuration(
    tenant_id: str,
    payload: TenantConfigurationUpdateRequest,
    claims: AuthClaims = Depends(require_scope("control:config:write")),
    session: AsyncSession = Depends(get_db_session),
) -> TenantConfigurationDTO:
    enforce_tenant_access(claims, tenant_id)
    tenant = await ControlRepository.get_tenant(session, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    current = await ControlRepository.get_tenant_configuration(session, tenant_id)

    anomaly_threshold = payload.anomaly_threshold if payload.anomaly_threshold is not None else current["anomaly_threshold"]
    if anomaly_threshold is not None and anomaly_threshold < 0:
        raise HTTPException(status_code=422, detail="anomaly_threshold must be >= 0")

    enabled_connectors = payload.enabled_connectors if payload.enabled_connectors is not None else current["enabled_connectors"]
    enabled_connectors = sorted({str(item) for item in enabled_connectors})
    missing_connectors = await ControlRepository.validate_connectors_exist(session, enabled_connectors)
    if missing_connectors:
        raise HTTPException(status_code=422, detail=f"Unknown connectors: {', '.join(missing_connectors)}")

    overrides = payload.rule_overrides_json if payload.rule_overrides_json is not None else current["rule_overrides_json"]
    overrides = _normalize_rule_overrides(overrides)

    model_version = payload.model_version if payload.model_version is not None else current["model_version"]
    active_global_version = await ControlRepository.get_active_global_model_version(session)
    if model_version and active_global_version and model_version != active_global_version:
        raise HTTPException(
            status_code=422,
            detail=(
                "tenant model_version must match current global active model version or be null "
                f"(active={active_global_version})"
            ),
        )

    try:
        updated = await ControlRepository.upsert_tenant_configuration(
            session,
            tenant_id=tenant_id,
            anomaly_threshold=anomaly_threshold,
            enabled_connectors=enabled_connectors,
            model_version=model_version,
            rule_overrides_json=overrides,
            expected_version=payload.expected_version,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    await ControlRepository.write_config_audit(
        session,
        tenant_id=tenant_id,
        actor=claims.sub,
        action="upsert",
        resource_type="tenant_configuration",
        resource_id=tenant_id,
        before_json=current,
        after_json=updated,
    )

    return TenantConfigurationDTO(**updated)


@router.get("/connectors/catalog", response_model=list[ConnectorCatalogItem])
async def connector_catalog(
    _: AuthClaims = Depends(require_scope("control:config:read")),
    session: AsyncSession = Depends(get_db_session),
) -> list[ConnectorCatalogItem]:
    rows = await ControlRepository.list_connector_catalog(session)
    return [ConnectorCatalogItem(**row) for row in rows]


@router.get("/tenants/{tenant_id}/connectors", response_model=TenantConnectorPolicyResponse)
async def get_tenant_connectors(
    tenant_id: str,
    claims: AuthClaims = Depends(require_scope("control:config:read")),
    session: AsyncSession = Depends(get_db_session),
) -> TenantConnectorPolicyResponse:
    enforce_tenant_access(claims, tenant_id)
    tenant = await ControlRepository.get_tenant(session, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    config = await ControlRepository.get_tenant_configuration(session, tenant_id)
    catalog = await ControlRepository.list_connector_catalog(session)
    return TenantConnectorPolicyResponse(
        tenant_id=tenant_id,
        enabled_connectors=config["enabled_connectors"],
        all_sources=[ConnectorCatalogItem(**item) for item in catalog],
    )


@router.put("/tenants/{tenant_id}/connectors", response_model=TenantConfigurationDTO)
async def put_tenant_connectors(
    tenant_id: str,
    payload: TenantConnectorPolicyUpdateRequest,
    claims: AuthClaims = Depends(require_scope("control:config:write")),
    session: AsyncSession = Depends(get_db_session),
) -> TenantConfigurationDTO:
    enforce_tenant_access(claims, tenant_id)
    current = await ControlRepository.get_tenant_configuration(session, tenant_id)
    missing_connectors = await ControlRepository.validate_connectors_exist(session, payload.enabled_connectors)
    if missing_connectors:
        raise HTTPException(status_code=422, detail=f"Unknown connectors: {', '.join(missing_connectors)}")

    try:
        updated = await ControlRepository.upsert_tenant_configuration(
            session,
            tenant_id=tenant_id,
            anomaly_threshold=current["anomaly_threshold"],
            enabled_connectors=sorted({str(item) for item in payload.enabled_connectors}),
            model_version=current["model_version"],
            rule_overrides_json=current["rule_overrides_json"],
            expected_version=payload.expected_version,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    await ControlRepository.write_config_audit(
        session,
        tenant_id=tenant_id,
        actor=claims.sub,
        action="update_connectors",
        resource_type="tenant_configuration",
        resource_id=tenant_id,
        before_json=current,
        after_json=updated,
    )
    return TenantConfigurationDTO(**updated)


@router.post("/connectors/{source_name}/run-now")
async def connector_run_now(
    source_name: str,
    claims: AuthClaims = Depends(require_scope("control:config:write")),
) -> dict[str, Any]:
    if not is_platform_operator(claims):
        raise HTTPException(status_code=403, detail="Platform operator scope required")
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(f"{settings.data_connector_url}/v1/connectors/run-now", params={"source_name": source_name})
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()


@router.post("/connectors/{source_name}/global-enable")
async def connector_global_enable(
    source_name: str,
    claims: AuthClaims = Depends(require_scope("control:config:write")),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    if not is_platform_operator(claims):
        raise HTTPException(status_code=403, detail="Platform operator scope required")
    updated = await ControlRepository.set_global_connector_enabled(session, source_name=source_name, enabled=True)
    if not updated:
        raise HTTPException(status_code=404, detail="Unknown source")

    await ControlRepository.write_config_audit(
        session,
        tenant_id=None,
        actor=claims.sub,
        action="global_enable",
        resource_type="connector",
        resource_id=source_name,
        before_json={},
        after_json={"enabled": True},
    )
    return {"status": "ok", "source_name": source_name, "enabled": True}


@router.post("/connectors/{source_name}/global-disable")
async def connector_global_disable(
    source_name: str,
    claims: AuthClaims = Depends(require_scope("control:config:write")),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    if not is_platform_operator(claims):
        raise HTTPException(status_code=403, detail="Platform operator scope required")
    updated = await ControlRepository.set_global_connector_enabled(session, source_name=source_name, enabled=False)
    if not updated:
        raise HTTPException(status_code=404, detail="Unknown source")

    await ControlRepository.write_config_audit(
        session,
        tenant_id=None,
        actor=claims.sub,
        action="global_disable",
        resource_type="connector",
        resource_id=source_name,
        before_json={},
        after_json={"enabled": False},
    )
    return {"status": "ok", "source_name": source_name, "enabled": False}


@router.get("/models")
async def list_models(
    _: AuthClaims = Depends(require_scope("control:config:read")),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict[str, Any]]:
    rows = await session.execute(
        text(
            """
            SELECT model_name, model_version, metadata, active, updated_at
            FROM model_registry
            ORDER BY updated_at DESC
            """
        )
    )
    return [dict(row._mapping) for row in rows]


@router.post("/models/activate-global")
async def activate_global_model(
    payload: ModelActivateRequest,
    claims: AuthClaims = Depends(require_scope("control:config:write")),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    if not is_platform_operator(claims):
        raise HTTPException(status_code=403, detail="Platform operator scope required")
    before_active = await ControlRepository.get_active_global_model_version(session)
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"{settings.ml_inference_url}/v1/models/activate",
            json=payload.model_dump(),
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    body = response.json()
    await ControlRepository.write_config_audit(
        session,
        tenant_id=None,
        actor=claims.sub,
        action="activate_global_model",
        resource_type="model",
        resource_id=f"{payload.model_name}:{payload.model_version}",
        before_json={"active_model_version": before_active},
        after_json=body,
    )
    return body


@router.put("/tenants/{tenant_id}/model-policy", response_model=TenantConfigurationDTO)
async def put_tenant_model_policy(
    tenant_id: str,
    payload: ModelPolicyUpdateRequest,
    claims: AuthClaims = Depends(require_scope("control:config:write")),
    session: AsyncSession = Depends(get_db_session),
) -> TenantConfigurationDTO:
    enforce_tenant_access(claims, tenant_id)
    current = await ControlRepository.get_tenant_configuration(session, tenant_id)

    active_global_version = await ControlRepository.get_active_global_model_version(session)
    if payload.model_version and active_global_version and payload.model_version != active_global_version:
        raise HTTPException(
            status_code=422,
            detail=(
                "tenant model_version must match current global active model version or be null "
                f"(active={active_global_version})"
            ),
        )

    try:
        updated = await ControlRepository.upsert_tenant_configuration(
            session,
            tenant_id=tenant_id,
            anomaly_threshold=current["anomaly_threshold"],
            enabled_connectors=current["enabled_connectors"],
            model_version=payload.model_version,
            rule_overrides_json=current["rule_overrides_json"],
            expected_version=payload.expected_version,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    await ControlRepository.write_config_audit(
        session,
        tenant_id=tenant_id,
        actor=claims.sub,
        action="update_model_policy",
        resource_type="tenant_configuration",
        resource_id=tenant_id,
        before_json=current,
        after_json=updated,
    )
    return TenantConfigurationDTO(**updated)


@router.post("/tenants/{tenant_id}/test-datasets/uploads", response_model=TestDatasetSummary)
async def upload_test_dataset(
    tenant_id: str,
    payload: TestDatasetUploadRequest,
    claims: AuthClaims = Depends(require_scope("control:testlab:write")),
    session: AsyncSession = Depends(get_db_session),
) -> TestDatasetSummary:
    enforce_tenant_access(claims, tenant_id)
    if not payload.events:
        raise HTTPException(status_code=422, detail="events payload is required")
    created = await ControlRepository.create_test_dataset(
        session,
        tenant_id=tenant_id,
        name=payload.name,
        source_type=payload.source_type,
        events=payload.events,
        uploaded_by=claims.sub,
    )
    return TestDatasetSummary(**created)


@router.post("/tenants/{tenant_id}/test-runs", response_model=TestRunSummary)
async def create_test_run(
    tenant_id: str,
    payload: TestRunCreateRequest,
    claims: AuthClaims = Depends(require_scope("control:testlab:write")),
    session: AsyncSession = Depends(get_db_session),
) -> TestRunSummary:
    enforce_tenant_access(claims, tenant_id)
    if payload.dataset_id is None and not payload.events:
        raise HTTPException(status_code=422, detail="dataset_id or events is required")

    if payload.dataset_id is not None:
        events = await ControlRepository.fetch_test_dataset_events(session, tenant_id=tenant_id, dataset_id=payload.dataset_id)
    else:
        events = payload.events or []

    run = await ControlRepository.create_test_run(
        session,
        tenant_id=tenant_id,
        dataset_id=payload.dataset_id,
        created_by=claims.sub,
    )
    run_id = UUID(str(run["run_id"]))

    service_token = create_access_token(
        subject=claims.sub,
        secret_key=settings.jwt_signing_key,
        algorithm=settings.jwt_algorithm,
        expires_minutes=10,
        tenant_id=tenant_id,
        roles=["admin"],
        scopes=["events:write", "events:read", "alerts:read", "alerts:write", "models:read", "connectors:read"],
    )

    ingest_results: list[dict[str, Any]] = []
    accepted_event_ids: list[UUID] = []

    async with httpx.AsyncClient(timeout=30) as client:
        for raw in events:
            try:
                validated = RiskEventIngestRequest(**raw)
            except Exception as exc:  # noqa: BLE001
                await ControlRepository.append_test_run_result(
                    session,
                    run_id=run_id,
                    event_id=None,
                    ingest_status="failed",
                    queued=False,
                    decision_found=False,
                    risk_level=None,
                    risk_score=None,
                    alert_found=False,
                    details={"validation_error": str(exc), "raw": raw},
                )
                ingest_results.append({"status": "failed", "error": str(exc), "event_id": None})
                continue

            try:
                response = await client.post(
                    f"{settings.api_gateway_url}/v2/events/ingest",
                    headers={"Authorization": f"Bearer {service_token}"},
                    json=validated.model_dump(mode="json"),
                )
                if response.status_code >= 400:
                    detail = response.text
                    event_id = validated.event_id
                    await ControlRepository.append_test_run_result(
                        session,
                        run_id=run_id,
                        event_id=event_id,
                        ingest_status="failed",
                        queued=False,
                        decision_found=False,
                        risk_level=None,
                        risk_score=None,
                        alert_found=False,
                        details={"http_status": response.status_code, "detail": detail},
                    )
                    ingest_results.append({"status": "failed", "event_id": str(event_id), "error": detail})
                    continue

                body = response.json()
                event_id = UUID(str(body.get("event_id")))
                status = str(body.get("status") or "failed")
                queued = bool(body.get("queued"))
                if status == "accepted":
                    accepted_event_ids.append(event_id)
                ingest_results.append({"status": status, "queued": queued, "event_id": str(event_id)})

                await ControlRepository.append_test_run_result(
                    session,
                    run_id=run_id,
                    event_id=event_id,
                    ingest_status=status,
                    queued=queued,
                    decision_found=False,
                    risk_level=None,
                    risk_score=None,
                    alert_found=False,
                    details={"ingest_response": body},
                )
            except Exception as exc:  # noqa: BLE001
                await ControlRepository.append_test_run_result(
                    session,
                    run_id=run_id,
                    event_id=validated.event_id,
                    ingest_status="failed",
                    queued=False,
                    decision_found=False,
                    risk_level=None,
                    risk_score=None,
                    alert_found=False,
                    details={"http_error": str(exc)},
                )
                ingest_results.append({"status": "failed", "event_id": str(validated.event_id), "error": str(exc)})

    if accepted_event_ids:
        await asyncio.sleep(1.0)

    decisions_found = 0
    alerts_found = 0
    for event_id in accepted_event_ids:
        decision, alert = await ControlRepository.fetch_decision_and_alert(session, tenant_id=tenant_id, event_id=event_id)
        if decision:
            decisions_found += 1
        if alert:
            alerts_found += 1
        await ControlRepository.append_test_run_result(
            session,
            run_id=run_id,
            event_id=event_id,
            ingest_status="observed",
            queued=True,
            decision_found=decision is not None,
            risk_level=str(decision.get("risk_level")) if decision else None,
            risk_score=float(decision.get("risk_score")) if decision and decision.get("risk_score") is not None else None,
            alert_found=alert is not None,
            details={"decision": decision or {}, "alert": alert or {}},
        )

    summary = {
        "ingested_total": len(events),
        "accepted": len([item for item in ingest_results if item.get("status") == "accepted"]),
        "duplicates": len([item for item in ingest_results if item.get("status") == "duplicate"]),
        "failed": len([item for item in ingest_results if item.get("status") == "failed"]),
        "decisions_found": decisions_found,
        "alerts_found": alerts_found,
    }

    completed = await ControlRepository.complete_test_run(
        session,
        run_id=run_id,
        status="completed",
        summary_json=summary,
    )
    return TestRunSummary(**completed)


@router.get("/tenants/{tenant_id}/test-runs", response_model=list[TestRunSummary])
async def list_test_runs(
    tenant_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    claims: AuthClaims = Depends(require_scope("control:config:read")),
    session: AsyncSession = Depends(get_db_session),
) -> list[TestRunSummary]:
    enforce_tenant_access(claims, tenant_id)
    rows = await ControlRepository.list_test_runs(session, tenant_id=tenant_id, limit=limit)
    return [TestRunSummary(**row) for row in rows]


@router.get("/tenants/{tenant_id}/test-runs/{run_id}", response_model=TestRunSummary)
async def get_test_run(
    tenant_id: str,
    run_id: UUID,
    claims: AuthClaims = Depends(require_scope("control:config:read")),
    session: AsyncSession = Depends(get_db_session),
) -> TestRunSummary:
    enforce_tenant_access(claims, tenant_id)
    item = await ControlRepository.get_test_run(session, tenant_id=tenant_id, run_id=run_id)
    if not item:
        raise HTTPException(status_code=404, detail="Test run not found")
    return TestRunSummary(**item)


@router.get("/tenants/{tenant_id}/test-runs/{run_id}/results", response_model=list[TestRunResultItem])
async def get_test_run_results(
    tenant_id: str,
    run_id: UUID,
    claims: AuthClaims = Depends(require_scope("control:config:read")),
    session: AsyncSession = Depends(get_db_session),
) -> list[TestRunResultItem]:
    enforce_tenant_access(claims, tenant_id)
    run = await ControlRepository.get_test_run(session, tenant_id=tenant_id, run_id=run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Test run not found")
    rows = await ControlRepository.list_test_run_results(session, run_id=run_id)
    return [TestRunResultItem(**row) for row in rows]


@router.get("/tenants/{tenant_id}/alert-destinations", response_model=list[AlertDestinationDTO])
async def list_alert_destinations(
    tenant_id: str,
    claims: AuthClaims = Depends(require_scope("control:routing:read")),
    session: AsyncSession = Depends(get_db_session),
) -> list[AlertDestinationDTO]:
    enforce_tenant_access(claims, tenant_id)
    rows = await ControlRepository.list_alert_destinations(session, tenant_id=tenant_id)
    return [AlertDestinationDTO(**row) for row in rows]


@router.post("/tenants/{tenant_id}/alert-destinations", response_model=AlertDestinationDTO)
async def create_alert_destination(
    tenant_id: str,
    payload: AlertDestinationCreateRequest,
    claims: AuthClaims = Depends(require_scope("control:routing:write")),
    session: AsyncSession = Depends(get_db_session),
) -> AlertDestinationDTO:
    enforce_tenant_access(claims, tenant_id)
    created = await ControlRepository.create_alert_destination(
        session,
        tenant_id=tenant_id,
        channel=payload.channel,
        name=payload.name,
        enabled=payload.enabled,
        config=payload.config,
        actor=claims.sub,
    )
    await ControlRepository.write_config_audit(
        session,
        tenant_id=tenant_id,
        actor=claims.sub,
        action="create",
        resource_type="alert_destination",
        resource_id=str(created["destination_id"]),
        before_json={},
        after_json=created,
    )
    return AlertDestinationDTO(**created)


@router.patch("/tenants/{tenant_id}/alert-destinations/{destination_id}", response_model=AlertDestinationDTO)
async def update_alert_destination(
    tenant_id: str,
    destination_id: UUID,
    payload: AlertDestinationUpdateRequest,
    claims: AuthClaims = Depends(require_scope("control:routing:write")),
    session: AsyncSession = Depends(get_db_session),
) -> AlertDestinationDTO:
    enforce_tenant_access(claims, tenant_id)
    before = await ControlRepository.get_alert_destination(session, tenant_id=tenant_id, destination_id=destination_id)
    if not before:
        raise HTTPException(status_code=404, detail="Destination not found")

    updated = await ControlRepository.update_alert_destination(
        session,
        tenant_id=tenant_id,
        destination_id=destination_id,
        name=payload.name,
        enabled=payload.enabled,
        config=payload.config,
        actor=claims.sub,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Destination not found")

    await ControlRepository.write_config_audit(
        session,
        tenant_id=tenant_id,
        actor=claims.sub,
        action="update",
        resource_type="alert_destination",
        resource_id=str(destination_id),
        before_json=before,
        after_json=updated,
    )
    return AlertDestinationDTO(**updated)


@router.delete("/tenants/{tenant_id}/alert-destinations/{destination_id}")
async def delete_alert_destination(
    tenant_id: str,
    destination_id: UUID,
    claims: AuthClaims = Depends(require_scope("control:routing:write")),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    enforce_tenant_access(claims, tenant_id)
    before = await ControlRepository.get_alert_destination(session, tenant_id=tenant_id, destination_id=destination_id)
    deleted = await ControlRepository.delete_alert_destination(session, tenant_id=tenant_id, destination_id=destination_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Destination not found")

    await ControlRepository.write_config_audit(
        session,
        tenant_id=tenant_id,
        actor=claims.sub,
        action="delete",
        resource_type="alert_destination",
        resource_id=str(destination_id),
        before_json=before or {},
        after_json={},
    )
    return {"status": "ok", "destination_id": str(destination_id), "deleted": True}


@router.post("/tenants/{tenant_id}/alert-destinations/{destination_id}/verify", response_model=AlertDestinationDTO)
async def verify_alert_destination(
    tenant_id: str,
    destination_id: UUID,
    claims: AuthClaims = Depends(require_scope("control:routing:write")),
    session: AsyncSession = Depends(get_db_session),
) -> AlertDestinationDTO:
    enforce_tenant_access(claims, tenant_id)
    destination = await ControlRepository.get_alert_destination(session, tenant_id=tenant_id, destination_id=destination_id)
    if not destination:
        raise HTTPException(status_code=404, detail="Destination not found")

    payload = {
        "alert_id": str(uuid4()),
        "event_id": str(uuid4()),
        "tenant_id": tenant_id,
        "severity": "critical",
        "risk_score": 0.99,
        "mode": "verification",
        "occurred_at": datetime.now(tz=UTC).isoformat(),
    }

    status, response_code, response_body, error_message = await _deliver_to_destination(
        destination=destination,
        alert_payload=payload,
        is_test=True,
    )

    await ControlRepository.create_delivery_log(
        session,
        tenant_id=tenant_id,
        destination_id=destination_id,
        channel=destination["channel"],
        alert_key=str(payload["alert_id"]),
        event_id=UUID(str(payload["event_id"])),
        status=status,
        attempt_no=1,
        response_code=response_code,
        response_body=response_body,
        error_message=error_message,
        payload_json=payload,
        is_test=True,
        delivered=status == "delivered",
    )

    updated = await ControlRepository.mark_destination_verification(
        session,
        tenant_id=tenant_id,
        destination_id=destination_id,
        status="verified" if status == "delivered" else "failed",
        actor=claims.sub,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Destination not found")
    return AlertDestinationDTO(**updated)


@router.get("/tenants/{tenant_id}/alert-routing-policy", response_model=AlertRoutingPolicyDTO)
async def get_alert_routing_policy(
    tenant_id: str,
    claims: AuthClaims = Depends(require_scope("control:routing:read")),
    session: AsyncSession = Depends(get_db_session),
) -> AlertRoutingPolicyDTO:
    enforce_tenant_access(claims, tenant_id)
    policy = await ControlRepository.get_alert_routing_policy(session, tenant_id=tenant_id)
    return AlertRoutingPolicyDTO(**policy)


@router.put("/tenants/{tenant_id}/alert-routing-policy", response_model=AlertRoutingPolicyDTO)
async def put_alert_routing_policy(
    tenant_id: str,
    payload: AlertRoutingPolicyUpdateRequest,
    claims: AuthClaims = Depends(require_scope("control:routing:write")),
    session: AsyncSession = Depends(get_db_session),
) -> AlertRoutingPolicyDTO:
    enforce_tenant_access(claims, tenant_id)
    before = await ControlRepository.get_alert_routing_policy(session, tenant_id=tenant_id)
    updated = await ControlRepository.upsert_alert_routing_policy(
        session,
        tenant_id=tenant_id,
        policy_json=payload.policy_json,
        actor=claims.sub,
    )
    await ControlRepository.write_config_audit(
        session,
        tenant_id=tenant_id,
        actor=claims.sub,
        action="update",
        resource_type="alert_routing_policy",
        resource_id=tenant_id,
        before_json=before,
        after_json=updated,
    )
    return AlertRoutingPolicyDTO(**updated)


@router.post("/tenants/{tenant_id}/alert-routing/test", response_model=list[DeliveryResult])
async def test_alert_routing(
    tenant_id: str,
    payload: AlertRoutingTestRequest,
    claims: AuthClaims = Depends(require_scope("control:routing:write")),
    session: AsyncSession = Depends(get_db_session),
) -> list[DeliveryResult]:
    enforce_tenant_access(claims, tenant_id)
    destinations = await ControlRepository.list_alert_destinations(session, tenant_id=tenant_id)
    policy = await ControlRepository.get_alert_routing_policy(session, tenant_id=tenant_id)
    selected = _resolve_routing_destinations(destinations, policy["policy_json"], payload.severity)

    test_alert_id = str(uuid4())
    event_id = uuid4()
    alert_payload = {
        "alert_id": test_alert_id,
        "event_id": str(event_id),
        "tenant_id": tenant_id,
        "severity": payload.severity,
        "risk_score": 0.98,
        "payload": payload.payload,
        "occurred_at": datetime.now(tz=UTC).isoformat(),
        "test": True,
    }

    results: list[DeliveryResult] = []
    for destination in selected:
        status, response_code, response_body, error_message = await _deliver_to_destination(
            destination=destination,
            alert_payload=alert_payload,
            is_test=True,
        )
        await ControlRepository.create_delivery_log(
            session,
            tenant_id=tenant_id,
            destination_id=UUID(str(destination["destination_id"])),
            channel=destination["channel"],
            alert_key=test_alert_id,
            event_id=event_id,
            status=status,
            attempt_no=1,
            response_code=response_code,
            response_body=response_body,
            error_message=error_message,
            payload_json=alert_payload,
            is_test=True,
            delivered=status == "delivered",
        )
        results.append(
            DeliveryResult(
                destination_id=UUID(str(destination["destination_id"])),
                channel=destination["channel"],
                status=status,
                attempt_no=1,
                error_message=error_message,
            )
        )
    return results


@router.get("/tenants/{tenant_id}/reconciliation/ingestion", response_model=ReconciliationSummaryDTO)
async def reconciliation_ingestion(
    tenant_id: str,
    from_ts: datetime | None = Query(default=None),
    to_ts: datetime | None = Query(default=None),
    claims: AuthClaims = Depends(require_scope("control:reports:read")),
    session: AsyncSession = Depends(get_db_session),
) -> ReconciliationSummaryDTO:
    enforce_tenant_access(claims, tenant_id)
    start, end = _parse_time_window(from_ts=from_ts, to_ts=to_ts, default_hours=24)
    ingestion = await ControlRepository.reconciliation_ingestion_summary(session, tenant_id=tenant_id, from_ts=start, to_ts=end)
    delivery = await ControlRepository.reconciliation_delivery_summary(session, tenant_id=tenant_id, from_ts=start, to_ts=end)

    mismatch = max(0, ingestion["ingested_events"] - ingestion["processed_decisions"]) + delivery["failed_deliveries"]
    return ReconciliationSummaryDTO(
        tenant_id=tenant_id,
        from_ts=start,
        to_ts=end,
        ingested_events=ingestion["ingested_events"],
        processed_decisions=ingestion["processed_decisions"],
        raised_alerts=ingestion["raised_alerts"],
        delivered_alerts=delivery["delivered_alerts"],
        failed_deliveries=delivery["failed_deliveries"],
        mismatch_count=mismatch,
    )


@router.get("/tenants/{tenant_id}/reconciliation/delivery", response_model=ReconciliationSummaryDTO)
async def reconciliation_delivery(
    tenant_id: str,
    from_ts: datetime | None = Query(default=None),
    to_ts: datetime | None = Query(default=None),
    claims: AuthClaims = Depends(require_scope("control:reports:read")),
    session: AsyncSession = Depends(get_db_session),
) -> ReconciliationSummaryDTO:
    enforce_tenant_access(claims, tenant_id)
    start, end = _parse_time_window(from_ts=from_ts, to_ts=to_ts, default_hours=24)
    ingestion = await ControlRepository.reconciliation_ingestion_summary(session, tenant_id=tenant_id, from_ts=start, to_ts=end)
    delivery = await ControlRepository.reconciliation_delivery_summary(session, tenant_id=tenant_id, from_ts=start, to_ts=end)
    mismatch = max(0, ingestion["raised_alerts"] - delivery["delivered_alerts"]) + delivery["failed_deliveries"]
    return ReconciliationSummaryDTO(
        tenant_id=tenant_id,
        from_ts=start,
        to_ts=end,
        ingested_events=ingestion["ingested_events"],
        processed_decisions=ingestion["processed_decisions"],
        raised_alerts=ingestion["raised_alerts"],
        delivered_alerts=delivery["delivered_alerts"],
        failed_deliveries=delivery["failed_deliveries"],
        mismatch_count=mismatch,
    )


@router.get("/tenants/{tenant_id}/reconciliation/export")
async def reconciliation_export(
    tenant_id: str,
    from_ts: datetime | None = Query(default=None),
    to_ts: datetime | None = Query(default=None),
    claims: AuthClaims = Depends(require_scope("control:reports:read")),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    enforce_tenant_access(claims, tenant_id)
    start, end = _parse_time_window(from_ts=from_ts, to_ts=to_ts, default_hours=24)
    ingestion = await ControlRepository.reconciliation_ingestion_summary(session, tenant_id=tenant_id, from_ts=start, to_ts=end)
    delivery = await ControlRepository.reconciliation_delivery_summary(session, tenant_id=tenant_id, from_ts=start, to_ts=end)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "tenant_id",
            "from_ts",
            "to_ts",
            "ingested_events",
            "processed_decisions",
            "raised_alerts",
            "delivered_alerts",
            "failed_deliveries",
            "mismatch_count",
        ]
    )
    mismatch = max(0, ingestion["ingested_events"] - ingestion["processed_decisions"]) + delivery["failed_deliveries"]
    writer.writerow(
        [
            tenant_id,
            start.isoformat(),
            end.isoformat(),
            ingestion["ingested_events"],
            ingestion["processed_decisions"],
            ingestion["raised_alerts"],
            delivery["delivered_alerts"],
            delivery["failed_deliveries"],
            mismatch,
        ]
    )

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=reconciliation-{tenant_id}.csv"},
    )


@router.get("/delivery/logs", response_model=list[DeliveryLogItem])
async def delivery_logs(
    tenant_id: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    claims: AuthClaims = Depends(require_scope("control:routing:read")),
    session: AsyncSession = Depends(get_db_session),
) -> list[DeliveryLogItem]:
    scoped_tenant_id = tenant_id
    if not is_platform_operator(claims):
        scoped_tenant_id = claims.tenant_id
    rows = await ControlRepository.list_delivery_logs(session, tenant_id=scoped_tenant_id, limit=limit)
    return [DeliveryLogItem(**row) for row in rows]


@router.get("/audit/config-changes", response_model=list[ConfigAuditItem])
async def audit_config_changes(
    tenant_id: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    claims: AuthClaims = Depends(require_any_scope(["control:tenants:read", "control:config:read"])),
    session: AsyncSession = Depends(get_db_session),
) -> list[ConfigAuditItem]:
    scoped_tenant_id = tenant_id
    if not is_platform_operator(claims):
        scoped_tenant_id = claims.tenant_id
    rows = await ControlRepository.list_config_audit(session, tenant_id=scoped_tenant_id, limit=limit)
    return [ConfigAuditItem(**row) for row in rows]
