from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, Request

from app.application.connectors import BinlistConnector, IpinfoConnector
from app.infrastructure.repository import ConnectorRepository

router = APIRouter(prefix="/v1/connectors", tags=["connectors"])


@router.get("/status")
async def connector_status(request: Request) -> list[dict]:
    async with request.app.state.db_session_factory() as session:
        return await ConnectorRepository.list_status(session)


@router.get("/runs")
async def connector_runs(
    request: Request,
    source_name: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict]:
    async with request.app.state.db_session_factory() as session:
        return await ConnectorRepository.list_runs(session, source_name=source_name, limit=limit)


@router.get("/errors")
async def connector_errors(
    request: Request,
    source_name: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict]:
    async with request.app.state.db_session_factory() as session:
        return await ConnectorRepository.list_errors(session, source_name=source_name, limit=limit)


@router.post("/run-now")
async def run_connectors_now(
    request: Request,
    source_name: str | None = Query(default=None),
) -> dict:
    scheduler = request.app.state.scheduler
    if source_name and source_name not in scheduler.connector_map:
        raise HTTPException(status_code=404, detail=f"Unknown source: {source_name}")
    await scheduler.run_once(source_name=source_name)
    return {"status": "ok", "triggered": True, "source_name": source_name}


@router.post("/enable")
async def enable_source(
    request: Request,
    source_name: str = Query(..., min_length=2, max_length=120),
) -> dict:
    async with request.app.state.db_session_factory() as session:
        updated = await ConnectorRepository.set_source_enabled(session, source_name=source_name, enabled=True)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Unknown source: {source_name}")
    return {"status": "ok", "source_name": source_name, "enabled": True}


@router.post("/disable")
async def disable_source(
    request: Request,
    source_name: str = Query(..., min_length=2, max_length=120),
) -> dict:
    async with request.app.state.db_session_factory() as session:
        updated = await ConnectorRepository.set_source_enabled(session, source_name=source_name, enabled=False)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Unknown source: {source_name}")
    return {"status": "ok", "source_name": source_name, "enabled": False}


@router.get("/lookup/ip")
async def lookup_ip(
    request: Request,
    ip: str = Query(..., min_length=7, max_length=64),
) -> dict:
    async with request.app.state.db_session_factory() as session:
        runtime = await ConnectorRepository.source_runtime(session, "ipinfo")
    if not runtime or not bool(runtime.get("source_enabled", False)) or not bool(runtime.get("state_enabled", False)):
        raise HTTPException(status_code=503, detail="ipinfo source disabled")

    scheduler = request.app.state.scheduler
    connector = scheduler.connector_map.get("ipinfo")
    if not isinstance(connector, IpinfoConnector):
        raise HTTPException(status_code=503, detail="IP lookup connector unavailable")

    record = await connector.lookup_ip(ip)
    if not record:
        raise HTTPException(status_code=404, detail="IP intelligence not found")

    async with request.app.state.db_session_factory() as session:
        await ConnectorRepository.upsert_ip_intelligence(
            session,
            source_name="ipinfo",
            ip=ip,
            country_code=record.get("country_code"),
            asn=record.get("asn"),
            is_proxy=record.get("is_proxy"),
            risk_score=record.get("risk_score"),
            raw=record.get("raw") or {},
            ttl_seconds=86400,
        )
        await session.commit()

    return {
        "source_name": "ipinfo",
        "fetched_at": datetime.now(tz=UTC).isoformat(),
        "record": record,
    }


@router.get("/lookup/bin")
async def lookup_bin(
    request: Request,
    card_bin: str = Query(..., min_length=6, max_length=12),
) -> dict:
    async with request.app.state.db_session_factory() as session:
        runtime = await ConnectorRepository.source_runtime(session, "binlist")
    if not runtime or not bool(runtime.get("source_enabled", False)) or not bool(runtime.get("state_enabled", False)):
        raise HTTPException(status_code=503, detail="binlist source disabled")

    scheduler = request.app.state.scheduler
    connector = scheduler.connector_map.get("binlist")
    if not isinstance(connector, BinlistConnector):
        raise HTTPException(status_code=503, detail="BIN lookup connector unavailable")

    record = await connector.lookup_bin(card_bin)
    if not record:
        raise HTTPException(status_code=404, detail="BIN intelligence not found")

    async with request.app.state.db_session_factory() as session:
        await ConnectorRepository.upsert_bin_intelligence(
            session,
            source_name="binlist",
            bin_value=card_bin,
            country_code=record.get("country_code"),
            issuer=record.get("issuer"),
            card_type=record.get("card_type"),
            card_brand=record.get("card_brand"),
            prepaid=record.get("prepaid"),
            raw=record.get("raw") or {},
            ttl_seconds=2592000,
        )
        await session.commit()

    return {
        "source_name": "binlist",
        "fetched_at": datetime.now(tz=UTC).isoformat(),
        "record": record,
    }
