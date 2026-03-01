from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.infrastructure.connector_repository import ConnectorRepository

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
    await scheduler.run_once(source_name=source_name, force=True)
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

