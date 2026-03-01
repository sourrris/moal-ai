"""Tests for environment variable aliases in backend settings."""

import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "libs" / "common"))

from risk_common.config import ApiGatewaySettings


def test_settings_accept_standardized_env_aliases(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure standardized env var names populate service settings."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@db:5432/app")
    monkeypatch.setenv("REDIS_URL", "redis://cache:6379/1")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("RABBITMQ_URL", "amqp://guest:guest@mq:5672/")

    settings = ApiGatewaySettings()

    assert settings.postgres_dsn == "postgresql+asyncpg://user:pass@db:5432/app"
    assert settings.redis_url == "redis://cache:6379/1"
    assert settings.jwt_secret_key == "test-secret"
    assert settings.rabbitmq_url == "amqp://guest:guest@mq:5672/"
