from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def persist_inference(
    session: AsyncSession,
    event_id: UUID,
    model_name: str,
    model_version: str,
    score: float,
    threshold: float,
    is_anomaly: bool,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO anomaly_results (event_id, model_name, model_version, anomaly_score, threshold, is_anomaly)
            VALUES (:event_id, :model_name, :model_version, :score, :threshold, :is_anomaly)
            """
        ),
        {
            "event_id": str(event_id),
            "model_name": model_name,
            "model_version": model_version,
            "score": score,
            "threshold": threshold,
            "is_anomaly": is_anomaly,
        },
    )

    status = "anomaly" if is_anomaly else "processed"
    await session.execute(
        text("UPDATE events SET status = :status WHERE event_id = :event_id"),
        {"status": status, "event_id": str(event_id)},
    )
    await session.commit()


async def mark_failed(session: AsyncSession, event_id: UUID) -> None:
    await session.execute(
        text("UPDATE events SET status = 'failed' WHERE event_id = :event_id"),
        {"event_id": str(event_id)},
    )
    await session.commit()
