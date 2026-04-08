from __future__ import annotations

from passlib.context import CryptContext
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pwd_context = CryptContext(schemes=["argon2", "bcrypt"], deprecated="auto")


class _UserRow:
    def __init__(self, username: str, password_hash: str, role: str) -> None:
        self.username = username
        self.password_hash = password_hash
        self.role = role


class UserRepository:
    @staticmethod
    def verify_password_and_upgrade_hash(
        password: str,
        stored_hash: str,
    ) -> tuple[bool, str | None]:
        """Verify a password against a stored hash.

        Returns (is_valid, upgraded_hash_or_none). If the hash needs upgrading
        (e.g. legacy plaintext or weak bcrypt round), the new argon2 hash is returned.
        """
        if pwd_context.identify(stored_hash) is None:
            # Plaintext legacy credential
            if password == stored_hash:
                return True, pwd_context.hash(password)
            return False, None

        is_valid, new_hash = pwd_context.verify_and_update(password, stored_hash)
        return is_valid, new_hash

    @staticmethod
    async def get_by_username(session: AsyncSession, username: str) -> _UserRow | None:
        result = await session.execute(
            text("SELECT username, password_hash, role FROM users WHERE username = :username"),
            {"username": username},
        )
        row = result.mappings().fetchone()
        if not row:
            return None
        return _UserRow(username=row["username"], password_hash=row["password_hash"], role=row["role"])

    @staticmethod
    async def authenticate(session: AsyncSession, username: str, password: str) -> _UserRow | None:
        user = await UserRepository.get_by_username(session, username)
        if not user:
            return None

        is_valid, upgraded_hash = UserRepository.verify_password_and_upgrade_hash(password, user.password_hash)
        if not is_valid:
            return None

        if upgraded_hash:
            await session.execute(
                text("UPDATE users SET password_hash = :hash WHERE username = :username"),
                {"hash": upgraded_hash, "username": username},
            )
            await session.commit()

        return user

    @staticmethod
    async def create_user(session: AsyncSession, username: str, password: str) -> _UserRow:
        hashed = pwd_context.hash(password)
        await session.execute(
            text("""
                INSERT INTO users (username, password_hash, role)
                VALUES (:username, :password_hash, 'analyst')
            """),
            {"username": username, "password_hash": hashed},
        )
        await session.commit()
        return _UserRow(username=username, password_hash=hashed, role="analyst")
