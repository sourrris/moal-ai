import json
import hashlib
from datetime import UTC, datetime
from uuid import UUID

from passlib.context import CryptContext
from risk_common.schemas import EventEnvelope
from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Event, User
from app.infrastructure.db import set_tenant_context

pwd_context = CryptContext(schemes=["argon2", "bcrypt"], deprecated="auto")


def _coerce_json_object(value: object) -> dict:
    if value is None:
        return {}

    candidate = value
    if isinstance(candidate, str):
        try:
            candidate = json.loads(candidate)
        except json.JSONDecodeError:
            return {"raw": candidate}

    if isinstance(candidate, dict):
        return candidate

    if hasattr(candidate, "items"):
        return dict(candidate)

    return {"value": candidate}


class UserRepository:
    ROLE_DEFAULT_SCOPES: dict[str, list[str]] = {
        "admin": [
            "events:write", "events:read",
            "alerts:write", "alerts:read",
            "models:read", "models:write",
            "connectors:read",
            "control:tenants:read", "control:tenants:write",
            "control:config:read", "control:config:write",
            "control:routing:read", "control:routing:write",
            "control:reports:read", "control:testlab:write",
        ],
        "analyst": ["events:read", "alerts:read", "alerts:write", "models:read"],
        "viewer": ["events:read", "alerts:read", "models:read"],
    }

    @staticmethod
    def hash_password(password: str) -> str:
        return pwd_context.hash(password)

    @staticmethod
    def verify_password_and_upgrade_hash(password: str, stored_hash: str) -> tuple[bool, str | None]:
        """Validate password against stored credentials and return optional upgraded hash.

        Supports legacy plaintext credentials for backward compatibility, returning
        an argon2 hash upgrade when legacy format is encountered.
        """
        identified_scheme = pwd_context.identify(stored_hash)

        if identified_scheme is None:
            if stored_hash != password:
                return False, None
            return True, pwd_context.hash(password)

        if not pwd_context.verify(password, stored_hash):
            return False, None

        if pwd_context.needs_update(stored_hash):
            return True, pwd_context.hash(password)

        return True, None

    @staticmethod
    async def authenticate(session: AsyncSession, username: str, password: str) -> User | None:
        """Authenticate a user and opportunistically upgrade password hash format."""
        result = await session.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
        if not user:
            return None

        is_valid, upgraded_hash = UserRepository.verify_password_and_upgrade_hash(password, user.password_hash)
        if not is_valid:
            return None

        if upgraded_hash:
            user.password_hash = upgraded_hash
            await session.commit()

        return user



    @staticmethod
    async def get_by_username(session: AsyncSession, username: str) -> User | None:
        """Fetch a user by username."""
        result = await session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_or_create_social_user(session: AsyncSession, username: str) -> User:
        """Get or create a user account for social sign-in identity."""
        existing_user = await UserRepository.get_by_username(session, username)
        if existing_user:
            return existing_user

        social_password_hash = UserRepository.hash_password(f"social-login:{username}:{datetime.now(UTC).timestamp()}")
        user = User(username=username, password_hash=social_password_hash, role="analyst")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user

    @staticmethod
    async def resolve_tenant_context(
        session: AsyncSession,
        user: User,
        requested_tenant_id: str | None = None,
    ) -> dict:
        where_sql = "WHERE utr.user_id = :user_id"
        params: dict[str, object] = {"user_id": user.id}
        if requested_tenant_id:
            where_sql += " AND utr.tenant_id = :tenant_id"
            params["tenant_id"] = requested_tenant_id

        rows = await session.execute(
            text(
                """
                SELECT utr.tenant_id, utr.role_name, COALESCE(r.scopes, ARRAY[]::text[]) AS scopes
                FROM user_tenant_roles utr
                LEFT JOIN roles r ON r.role_name = utr.role_name
                """
                + where_sql
                + """
                ORDER BY utr.tenant_id ASC, utr.role_name ASC
                """
            ),
            params,
        )
        mappings = [dict(item._mapping) for item in rows]
        if mappings:
            tenant_id = str(mappings[0]["tenant_id"])
            role_set: set[str] = {str(item["role_name"]) for item in mappings if item.get("role_name")}
            scope_set: set[str] = set()
            for item in mappings:
                for scope in item.get("scopes") or []:
                    scope_set.add(str(scope))
            return {
                "tenant_id": tenant_id,
                "roles": sorted(role_set),
                "scopes": sorted(scope_set),
            }

        if not requested_tenant_id:
            return None
        fallback_role = (user.role or "analyst").strip() or "analyst"
        return {
            "tenant_id": requested_tenant_id,
            "roles": [fallback_role],
            "scopes": UserRepository.ROLE_DEFAULT_SCOPES.get(fallback_role, UserRepository.ROLE_DEFAULT_SCOPES["viewer"]),
        }


class RefreshSessionRepository:
    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        session_id: UUID,
        username: str,
        tenant_id: str,
        refresh_token: str,
        expires_at: datetime,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> None:
        await session.execute(
            text(
                """
                INSERT INTO refresh_sessions (
                    session_id,
                    username,
                    tenant_id,
                    refresh_token_hash,
                    issued_at,
                    expires_at,
                    last_seen_at,
                    user_agent,
                    ip_address
                ) VALUES (
                    :session_id,
                    :username,
                    :tenant_id,
                    :refresh_token_hash,
                    NOW(),
                    :expires_at,
                    NOW(),
                    :user_agent,
                    :ip_address
                )
                """
            ),
            {
                "session_id": str(session_id),
                "username": username,
                "tenant_id": tenant_id,
                "refresh_token_hash": RefreshSessionRepository.hash_token(refresh_token),
                "expires_at": expires_at,
                "user_agent": user_agent,
                "ip_address": ip_address,
            },
        )
        await session.commit()

    @staticmethod
    async def get_active_by_session_id(session: AsyncSession, *, session_id: str) -> dict | None:
        row = await session.execute(
            text(
                """
                SELECT
                    session_id,
                    username,
                    tenant_id,
                    refresh_token_hash,
                    issued_at,
                    expires_at,
                    rotated_at,
                    revoked_at,
                    last_seen_at
                FROM refresh_sessions
                WHERE session_id = :session_id
                  AND revoked_at IS NULL
                LIMIT 1
                """
            ),
            {"session_id": session_id},
        )
        result = row.first()
        return dict(result._mapping) if result else None

    @staticmethod
    async def rotate(
        session: AsyncSession,
        *,
        session_id: str,
        current_refresh_token: str,
        next_refresh_token: str,
        expires_at: datetime,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> bool:
        result = await session.execute(
            text(
                """
                UPDATE refresh_sessions
                SET
                    refresh_token_hash = :next_hash,
                    expires_at = :expires_at,
                    rotated_at = NOW(),
                    last_seen_at = NOW(),
                    user_agent = COALESCE(:user_agent, user_agent),
                    ip_address = COALESCE(:ip_address, ip_address)
                WHERE session_id = :session_id
                  AND revoked_at IS NULL
                  AND expires_at > NOW()
                  AND refresh_token_hash = :current_hash
                """
            ),
            {
                "session_id": session_id,
                "current_hash": RefreshSessionRepository.hash_token(current_refresh_token),
                "next_hash": RefreshSessionRepository.hash_token(next_refresh_token),
                "expires_at": expires_at,
                "user_agent": user_agent,
                "ip_address": ip_address,
            },
        )
        await session.commit()
        return bool(result.rowcount)

    @staticmethod
    async def revoke(session: AsyncSession, *, session_id: str) -> None:
        await session.execute(
            text(
                """
                UPDATE refresh_sessions
                SET revoked_at = NOW(), last_seen_at = NOW()
                WHERE session_id = :session_id
                  AND revoked_at IS NULL
                """
            ),
            {"session_id": session_id},
        )
        await session.commit()

class EventRepository:
    PAYLOAD_JSON_SQL = (
        "CASE "
        "WHEN jsonb_typeof(e.payload::jsonb) = 'string' THEN (e.payload::jsonb #>> '{}')::jsonb "
        "ELSE e.payload::jsonb "
        "END"
    )
    RAW_DOMAIN_ID_SQL = (
        f"COALESCE({PAYLOAD_JSON_SQL} -> 'metadata' ->> 'registered_domain_id', {PAYLOAD_JSON_SQL} ->> 'registered_domain_id')"
    )
    DOMAIN_ID_SQL = f"COALESCE(td.domain_id::text, {RAW_DOMAIN_ID_SQL})"
    DOMAIN_HOSTNAME_SQL = (
        f"COALESCE(td.hostname, {PAYLOAD_JSON_SQL} -> 'metadata' ->> 'registered_domain', {PAYLOAD_JSON_SQL} ->> 'registered_domain')"
    )
    SEVERITY_SQL = "COALESCE(a.severity, rd.risk_level)"

    @staticmethod
    async def create_if_absent(
        session: AsyncSession,
        event: EventEnvelope,
        submitted_by: str,
    ) -> bool:
        stmt = (
            pg_insert(Event)
            .values(
                event_id=event.event_id,
                tenant_id=event.tenant_id,
                source=event.source,
                event_type=event.event_type,
                payload=event.payload,
                features=event.features,
                status="queued",
                submitted_by=submitted_by,
                occurred_at=event.occurred_at,
                ingested_at=event.ingested_at,
            )
            .on_conflict_do_nothing(index_elements=[Event.event_id])
        )
        result = await session.execute(stmt)
        await session.commit()
        return bool(result.rowcount)

    @staticmethod
    async def mark_status(session: AsyncSession, event_id: UUID, status: str) -> None:
        await session.execute(update(Event).where(Event.event_id == event_id).values(status=status))
        await session.commit()

    @staticmethod
    async def fetch_by_id(session: AsyncSession, event_id: UUID) -> Event | None:
        result = await session.execute(select(Event).where(Event.event_id == event_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def list_events(
        session: AsyncSession,
        *,
        tenant_id: str | None,
        domain_id: str | None,
        status: str | None,
        severity: str | None,
        source: str | None,
        event_type: str | None,
        from_ts: datetime | None,
        to_ts: datetime | None,
        page: int | None,
        cursor: str | None,
        limit: int,
    ) -> dict:
        if page is not None:
            offset = (page - 1) * limit
        else:
            try:
                offset = int(cursor or 0)
            except ValueError:
                offset = 0

        where_clauses = ["1=1"]
        params: dict = {"offset": offset, "limit": limit}

        if tenant_id:
            where_clauses.append("e.tenant_id = :tenant_id")
            params["tenant_id"] = tenant_id
        if domain_id:
            where_clauses.append(f"{EventRepository.DOMAIN_ID_SQL} = :domain_id")
            params["domain_id"] = domain_id
        if status:
            where_clauses.append("e.status = :status")
            params["status"] = status
        if severity:
            where_clauses.append(f"{EventRepository.SEVERITY_SQL} = :severity")
            params["severity"] = severity
        if source:
            where_clauses.append("e.source = :source")
            params["source"] = source
        if event_type:
            where_clauses.append("e.event_type = :event_type")
            params["event_type"] = event_type
        if from_ts:
            where_clauses.append("e.ingested_at >= :from_ts")
            params["from_ts"] = from_ts
        if to_ts:
            where_clauses.append("e.ingested_at <= :to_ts")
            params["to_ts"] = to_ts

        where_sql = " AND ".join(where_clauses)

        rows = await session.execute(
            text(
                f"""
                SELECT
                    e.event_id,
                    e.tenant_id,
                    e.source,
                    e.event_type,
                    e.status,
                    e.occurred_at,
                    e.ingested_at,
                    rd.risk_score,
                    rd.risk_level,
                    {EventRepository.SEVERITY_SQL} AS severity,
                    {EventRepository.DOMAIN_ID_SQL} AS domain_id,
                    {EventRepository.DOMAIN_HOSTNAME_SQL} AS domain_hostname
                FROM events e
                LEFT JOIN risk_decisions rd
                  ON rd.tenant_id = e.tenant_id
                 AND rd.event_id = e.event_id
                LEFT JOIN alerts_v2 a
                  ON a.tenant_id = e.tenant_id
                 AND a.event_id = e.event_id
                LEFT JOIN tenant_domains td
                  ON td.domain_id::text = {EventRepository.RAW_DOMAIN_ID_SQL}
                WHERE {where_sql}
                ORDER BY e.ingested_at DESC
                OFFSET :offset
                LIMIT :limit
                """
            ),
            params,
        )

        total = await session.execute(
            text(
                f"""
                SELECT COUNT(*) AS total
                FROM events e
                LEFT JOIN risk_decisions rd
                  ON rd.tenant_id = e.tenant_id
                 AND rd.event_id = e.event_id
                LEFT JOIN alerts_v2 a
                  ON a.tenant_id = e.tenant_id
                 AND a.event_id = e.event_id
                LEFT JOIN tenant_domains td
                  ON td.domain_id::text = {EventRepository.RAW_DOMAIN_ID_SQL}
                WHERE {where_sql}
                """
            ),
            params,
        )
        total_count = int(total.scalar_one() or 0)
        items = [dict(row._mapping) for row in rows]
        for item in items:
            if item.get("risk_score") is not None:
                item["risk_score"] = float(item["risk_score"])
        next_cursor = str(offset + limit) if offset + limit < total_count else None
        total_pages = max(1, (total_count + limit - 1) // limit) if limit else 1
        current_page = page if page is not None else (offset // limit) + 1 if limit else 1
        return {
            "items": items,
            "next_cursor": next_cursor,
            "total_estimate": total_count,
            "page": current_page,
            "page_size": limit,
            "total_pages": total_pages,
        }

    @staticmethod
    async def fetch_event_detail(session: AsyncSession, event_id: UUID) -> dict | None:
        row = await session.execute(
            text(
                """
                SELECT
                    e.event_id,
                    e.tenant_id,
                    e.source,
                    e.event_type,
                    e.status,
                    e.payload,
                    e.features,
                    e.submitted_by,
                    e.occurred_at,
                    e.ingested_at
                FROM events e
                WHERE e.event_id = :event_id
                """
            ),
            {"event_id": str(event_id)},
        )
        event = row.first()
        if not event:
            return None

        tenant_id = str(event._mapping.get("tenant_id") or "")
        if tenant_id:
            await set_tenant_context(session, tenant_id)

        processing = await session.execute(
            text(
                """
                SELECT
                    id,
                    model_name,
                    model_version,
                    anomaly_score,
                    threshold,
                    is_anomaly,
                    processed_at
                FROM anomaly_results
                WHERE event_id = :event_id
                ORDER BY processed_at ASC
                """
            ),
            {"event_id": str(event_id)},
        )
        decision = await session.execute(
            text(
                """
                SELECT
                    decision_id,
                    risk_score,
                    risk_level,
                    reasons,
                    rule_hits,
                    model_name,
                    model_version,
                    ml_anomaly_score,
                    ml_threshold,
                    decision_latency_ms,
                    created_at
                FROM risk_decisions
                WHERE tenant_id = :tenant_id
                  AND event_id = :event_id
                LIMIT 1
                """
            ),
            {"tenant_id": tenant_id, "event_id": str(event_id)},
        )
        payload = dict(event._mapping)
        payload["payload"] = _coerce_json_object(payload.get("payload"))
        processing_history = [dict(item._mapping) for item in processing]
        decision_item = decision.first()
        if decision_item:
            decision_payload = dict(decision_item._mapping)
            payload["risk_score"] = float(decision_payload.get("risk_score") or 0.0)
            payload["risk_level"] = str(decision_payload.get("risk_level") or "")
            payload["reasons"] = [str(item) for item in decision_payload.get("reasons") or []]
            payload["rule_hits"] = [str(item) for item in decision_payload.get("rule_hits") or []]
            payload["decision_latency_ms"] = decision_payload.get("decision_latency_ms")
            if not processing_history:
                processing_history = [
                    {
                        "id": str(decision_payload["decision_id"]),
                        "model_name": decision_payload["model_name"],
                        "model_version": decision_payload["model_version"],
                        "anomaly_score": float(decision_payload.get("ml_anomaly_score") or 0.0),
                        "threshold": float(decision_payload.get("ml_threshold") or 0.0),
                        "is_anomaly": payload["risk_level"] in {"high", "critical"},
                        "processed_at": decision_payload["created_at"],
                    }
                ]
        payload["processing_history"] = processing_history
        return payload


class MonitoringRepository:
    SEVERITY_SQL = (
        "CASE "
        "WHEN ar.anomaly_score >= ar.threshold * 2 THEN 'critical' "
        "WHEN ar.anomaly_score >= ar.threshold * 1.5 THEN 'high' "
        "ELSE 'medium' END"
    )

    @staticmethod
    async def overview_metrics(
        session: AsyncSession,
        *,
        tenant_id: str | None,
        from_ts: datetime,
        window_hours: int,
    ) -> dict:
        params: dict = {"from_ts": from_ts, "window_hours": max(1, window_hours)}
        tenant_events_clause = ""
        tenant_alerts_clause = ""
        if tenant_id:
            params["tenant_id"] = tenant_id
            tenant_events_clause = " AND e.tenant_id = :tenant_id "
            tenant_alerts_clause = " AND ev.tenant_id = :tenant_id "

        counts = await session.execute(
            text(
                f"""
                SELECT
                    COALESCE(SUM(CASE WHEN e.status = 'failed' THEN 1 ELSE 0 END), 0) AS failed_events,
                    COUNT(*) AS total_events
                FROM events e
                WHERE e.ingested_at >= :from_ts
                {tenant_events_clause}
                """
            ),
            params,
        )
        count_row = dict(counts.one()._mapping)

        anomalies = await session.execute(
            text(
                f"""
                SELECT COUNT(*) AS active_anomalies
                FROM anomaly_results ar
                JOIN events ev ON ev.event_id = ar.event_id
                WHERE ar.processed_at >= :from_ts
                {tenant_alerts_clause}
                """
            ),
            params,
        )
        active_anomalies = int(anomalies.scalar_one() or 0)

        total_events = int(count_row.get("total_events", 0) or 0)
        failed_events = int(count_row.get("failed_events", 0) or 0)
        failure_rate = (failed_events / total_events) if total_events else 0.0
        ingestion_rate = total_events / max(1, window_hours)
        alert_rate = active_anomalies / max(1, window_hours)

        model_health = max(0.0, min(100.0, (1.0 - (active_anomalies / max(1, total_events))) * 100))

        timeseries = await session.execute(
            text(
                f"""
                SELECT
                    date_trunc('hour', ar.processed_at) AS bucket,
                    AVG(ar.anomaly_score) AS avg_score,
                    AVG(ar.threshold) AS avg_threshold,
                    COUNT(*) AS anomaly_count
                FROM anomaly_results ar
                JOIN events ev ON ev.event_id = ar.event_id
                WHERE ar.processed_at >= :from_ts
                {tenant_alerts_clause}
                GROUP BY bucket
                ORDER BY bucket ASC
                """
            ),
            params,
        )

        severity = await session.execute(
            text(
                f"""
                SELECT
                    {MonitoringRepository.SEVERITY_SQL} AS severity,
                    COUNT(*) AS count
                FROM anomaly_results ar
                JOIN events ev ON ev.event_id = ar.event_id
                WHERE ar.processed_at >= :from_ts
                {tenant_alerts_clause}
                GROUP BY severity
                """
            ),
            params,
        )

        return {
            "active_anomalies": active_anomalies,
            "alert_rate": alert_rate,
            "ingestion_rate": ingestion_rate,
            "failure_rate": failure_rate,
            "model_health": model_health,
            "timeseries": [dict(row._mapping) for row in timeseries],
            "severity_distribution": [dict(row._mapping) for row in severity],
        }

    @staticmethod
    async def list_alerts(
        session: AsyncSession,
        *,
        tenant_id: str | None,
        severity: str | None,
        model_version: str | None,
        from_ts: datetime | None,
        to_ts: datetime | None,
        score_min: float | None,
        score_max: float | None,
        cursor: str | None,
        limit: int,
    ) -> dict:
        try:
            offset = int(cursor or 0)
        except ValueError:
            offset = 0
        params: dict = {"offset": offset, "limit": limit}
        where_clauses = ["1=1"]

        if tenant_id:
            where_clauses.append("e.tenant_id = :tenant_id")
            params["tenant_id"] = tenant_id
        if model_version:
            where_clauses.append("ar.model_version = :model_version")
            params["model_version"] = model_version
        if from_ts:
            where_clauses.append("ar.processed_at >= :from_ts")
            params["from_ts"] = from_ts
        if to_ts:
            where_clauses.append("ar.processed_at <= :to_ts")
            params["to_ts"] = to_ts
        if score_min is not None:
            where_clauses.append("ar.anomaly_score >= :score_min")
            params["score_min"] = score_min
        if score_max is not None:
            where_clauses.append("ar.anomaly_score <= :score_max")
            params["score_max"] = score_max
        if severity:
            where_clauses.append(f"{MonitoringRepository.SEVERITY_SQL} = :severity")
            params["severity"] = severity

        where_sql = " AND ".join(where_clauses)

        rows = await session.execute(
            text(
                f"""
                SELECT
                    ar.id AS numeric_alert_id,
                    ar.event_id,
                    e.tenant_id,
                    e.source,
                    e.event_type,
                    {MonitoringRepository.SEVERITY_SQL} AS severity,
                    ar.model_name,
                    ar.model_version,
                    ar.anomaly_score,
                    ar.threshold,
                    ar.processed_at AS created_at,
                    CONCAT(ar.event_id::text, '-', ar.id::text) AS alert_id
                FROM anomaly_results ar
                JOIN events e ON e.event_id = ar.event_id
                WHERE {where_sql}
                ORDER BY ar.processed_at DESC
                OFFSET :offset
                LIMIT :limit
                """
            ),
            params,
        )

        total = await session.execute(
            text(
                f"""
                SELECT COUNT(*) AS total
                FROM anomaly_results ar
                JOIN events e ON e.event_id = ar.event_id
                WHERE {where_sql}
                """
            ),
            params,
        )
        total_count = int(total.scalar_one() or 0)
        items = [dict(row._mapping) for row in rows]
        next_cursor = str(offset + limit) if offset + limit < total_count else None
        return {"items": items, "next_cursor": next_cursor, "total_estimate": total_count}

    @staticmethod
    async def fetch_alert_detail(session: AsyncSession, alert_id: str) -> dict | None:
        if "-" not in alert_id:
            return None
        base_event_id, numeric_id = alert_id.rsplit("-", 1)

        try:
            UUID(base_event_id)
            numeric_alert_id = int(numeric_id)
        except (ValueError, TypeError):
            return None

        row = await session.execute(
            text(
                f"""
                SELECT
                    ar.id AS numeric_alert_id,
                    ar.event_id,
                    e.tenant_id,
                    e.source,
                    e.event_type,
                    {MonitoringRepository.SEVERITY_SQL} AS severity,
                    ar.model_name,
                    ar.model_version,
                    ar.anomaly_score,
                    ar.threshold,
                    ar.is_anomaly,
                    ar.processed_at AS created_at,
                    e.payload AS event_payload,
                    CONCAT(ar.event_id::text, '-', ar.id::text) AS alert_id
                FROM anomaly_results ar
                JOIN events e ON e.event_id = ar.event_id
                WHERE ar.id = :numeric_alert_id
                  AND ar.event_id = :event_id
                LIMIT 1
                """
            ),
            {"numeric_alert_id": numeric_alert_id, "event_id": base_event_id},
        )

        result = row.first()
        if not result:
            return None

        payload = dict(result._mapping)
        payload["event_payload"] = _coerce_json_object(payload.get("event_payload"))
        return payload


class ModelRepository:
    @staticmethod
    async def list_models(session: AsyncSession) -> list[dict]:
        rows = await session.execute(
            text(
                """
                SELECT
                    ar.model_name,
                    ar.model_version,
                    AVG(ar.threshold) AS threshold,
                    MAX(ar.processed_at) AS updated_at,
                    COUNT(*) AS inference_count,
                    AVG(CASE WHEN ar.is_anomaly THEN 1 ELSE 0 END) AS anomaly_rate
                FROM anomaly_results ar
                GROUP BY ar.model_name, ar.model_version
                ORDER BY updated_at DESC
                """
            )
        )
        return [dict(row._mapping) for row in rows]

    @staticmethod
    async def model_metrics(session: AsyncSession, model_version: str) -> dict:
        summary = await session.execute(
            text(
                """
                SELECT
                    COUNT(*) AS total_inferences,
                    AVG(CASE WHEN is_anomaly THEN 1 ELSE 0 END) AS anomaly_hit_rate
                FROM anomaly_results
                WHERE model_version = :model_version
                """
            ),
            {"model_version": model_version},
        )
        summary_row = dict(summary.one()._mapping)

        training_summary_row = await session.execute(
            text(
                """
                SELECT
                    run_id,
                    model_name,
                    model_version,
                    status,
                    started_at,
                    finished_at,
                    initiated_by,
                    parameters,
                    metrics
                FROM model_training_runs
                WHERE model_version = :model_version
                  AND status = 'success'
                ORDER BY finished_at DESC NULLS LAST, started_at DESC
                LIMIT 1
                """
            ),
            {"model_version": model_version},
        )
        latest_training = training_summary_row.first()

        threshold_points = await session.execute(
            text(
                """
                SELECT
                    date_trunc('hour', processed_at) AS bucket,
                    AVG(threshold) AS avg_threshold,
                    AVG(anomaly_score) AS avg_score,
                    COUNT(*) AS volume
                FROM anomaly_results
                WHERE model_version = :model_version
                GROUP BY bucket
                ORDER BY bucket ASC
                """
            ),
            {"model_version": model_version},
        )

        latest_training_summary = None
        if latest_training:
            training_payload = dict(latest_training._mapping)
            metrics = (
                dict(training_payload["metrics"])
                if isinstance(training_payload.get("metrics"), dict)
                else {}
            )
            parameters = (
                dict(training_payload["parameters"])
                if isinstance(training_payload.get("parameters"), dict)
                else {}
            )
            dataset_summary = (
                dict(parameters.get("dataset_summary"))
                if isinstance(parameters.get("dataset_summary"), dict)
                else {}
            )
            sample_count = int(
                metrics.get("sample_count")
                or dataset_summary.get("effective_sample_count")
                or dataset_summary.get("raw_sample_count")
                or 0
            )
            latest_training_summary = {
                "run_id": training_payload.get("run_id"),
                "model_name": training_payload.get("model_name"),
                "model_version": training_payload.get("model_version"),
                "status": training_payload.get("status"),
                "started_at": training_payload.get("started_at"),
                "finished_at": training_payload.get("finished_at"),
                "initiated_by": training_payload.get("initiated_by"),
                "sample_count": sample_count,
                "train_loss": metrics.get("train_loss"),
                "val_loss": metrics.get("val_loss"),
                "threshold": metrics.get("threshold"),
                "threshold_quantile": metrics.get("threshold_quantile"),
                "dataset_lineage": (
                    dict(parameters.get("dataset_lineage"))
                    if isinstance(parameters.get("dataset_lineage"), dict)
                    else {}
                ),
                "dataset_summary": dataset_summary,
            }

        return {
            "model_version": model_version,
            "anomaly_hit_rate": float(summary_row.get("anomaly_hit_rate") or 0.0),
            "total_inferences": int(summary_row.get("total_inferences") or 0),
            "inference_latency_ms": {"p50": None, "p95": None},
            "threshold_evolution": [dict(row._mapping) for row in threshold_points],
            "latest_training_summary": latest_training_summary,
        }

    @staticmethod
    async def fetch_training_features(
        session: AsyncSession,
        *,
        tenant_id: str | None,
        lookback_hours: int,
        max_samples: int,
    ) -> list[list[float]]:
        if tenant_id:
            await set_tenant_context(session, tenant_id)

        where_clauses = [
            "feature_vector IS NOT NULL",
            "array_length(feature_vector, 1) IS NOT NULL",
            "created_at >= NOW() - make_interval(hours => :lookback_hours)",
        ]
        params: dict[str, object] = {
            "lookback_hours": int(lookback_hours),
            "max_samples": int(max_samples),
        }
        if tenant_id:
            where_clauses.append("tenant_id = :tenant_id")
            params["tenant_id"] = tenant_id

        where_sql = " AND ".join(where_clauses)
        rows = await session.execute(
            text(
                f"""
                SELECT feature_vector
                FROM risk_decisions
                WHERE {where_sql}
                ORDER BY created_at DESC
                LIMIT :max_samples
                """
            ),
            params,
        )

        features: list[list[float]] = []
        for row in rows:
            raw = row._mapping.get("feature_vector")
            if not raw:
                continue
            features.append([float(value) for value in raw])
        return features
