from __future__ import annotations

import logging

import bcrypt
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


class UserRepositoryError(Exception):
    """Base exception for UserRepository errors."""

    pass


class UserNotFoundError(UserRepositoryError):
    """Raised when a user is not found."""

    pass


class UserCreationError(UserRepositoryError):
    """Raised when user creation fails."""

    pass


class UserAuthenticationError(UserRepositoryError):
    """Raised when authentication operation fails."""

    pass


class _UserRow:
    def __init__(self, username: str, password_hash: str, role: str) -> None:
        self.username = username
        self.password_hash = password_hash
        self.role = role


class UserRepository:
    @staticmethod
    def verify_password(password: str, stored_hash: str) -> bool:
        try:
            # Handle legacy plaintext credentials
            if not stored_hash.startswith("$2"):
                return password == stored_hash
            return _verify_password(password, stored_hash)
        except Exception as e:
            logger.error(f"Error during password verification: {str(e)}")
            raise UserAuthenticationError(f"Password verification failed: {str(e)}") from e

    @staticmethod
    async def get_by_username(session: AsyncSession, username: str) -> _UserRow | None:
        try:
            result = await session.execute(
                text(
                    "SELECT username, password_hash, role FROM users WHERE username = :username"
                ),
                {"username": username},
            )
            row = result.mappings().fetchone()
            if not row:
                return None
            return _UserRow(
                username=row["username"],
                password_hash=row["password_hash"],
                role=row["role"],
            )
        except SQLAlchemyError as e:
            logger.error(f"Database error while fetching user {username}: {str(e)}")
            raise UserAuthenticationError(f"Failed to fetch user: {str(e)}") from e

    @staticmethod
    async def authenticate(
        session: AsyncSession, username: str, password: str
    ) -> _UserRow | None:
        try:
            user = await UserRepository.get_by_username(session, username)
            if not user:
                return None

            if not UserRepository.verify_password(password, user.password_hash):
                return None

            return user
        except UserRepositoryError:
            raise
        except Exception as e:
            logger.error(
                f"Unexpected error during authentication for {username}: {str(e)}"
            )
            raise UserAuthenticationError(f"Authentication failed: {str(e)}") from e

    @staticmethod
    async def create_user(
        session: AsyncSession, username: str, password: str
    ) -> _UserRow:
        try:
            hashed = _hash_password(password)
            await session.execute(
                text("""
                    INSERT INTO users (username, password_hash, role)
                    VALUES (:username, :password_hash, 'analyst')
                """),
                {"username": username, "password_hash": hashed},
            )
            await session.commit()
            return _UserRow(username=username, password_hash=hashed, role="analyst")
        except IntegrityError as e:
            await session.rollback()
            logger.error(
                f"User {username} already exists or constraint violation: {str(e)}"
            )
            raise UserCreationError(f"User {username} already exists") from e
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Database error while creating user {username}: {str(e)}")
            raise UserCreationError(f"Failed to create user: {str(e)}") from e
        except Exception as e:
            await session.rollback()
            logger.error(f"Unexpected error while creating user {username}: {str(e)}")
            raise UserCreationError(f"Failed to create user: {str(e)}") from e
