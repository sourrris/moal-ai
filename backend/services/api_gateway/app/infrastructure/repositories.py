from uuid import UUID

from passlib.context import CryptContext
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Event, User
from risk_common.schemas import EventEnvelope

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserRepository:
    @staticmethod
    async def authenticate(session: AsyncSession, username: str, password: str) -> User | None:
        result = await session.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
        if not user:
            return None

        # Allow plaintext seeds in local/dev while keeping bcrypt support for production.
        if user.password_hash.startswith("$2"):
            if not pwd_context.verify(password, user.password_hash):
                return None
        elif user.password_hash != password:
            return None
        return user


class EventRepository:
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
