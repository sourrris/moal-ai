"""Production secret validation tests for settings."""

import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "libs" / "common"))

from risk_common.config import ApiGatewaySettings


def test_production_settings_reject_placeholder_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET", "change-me-in-prod")
    monkeypatch.setenv("JWT_REFRESH_SECRET", "change-me-refresh-secret")
    with pytest.raises(ValueError):
        ApiGatewaySettings()


def test_production_settings_accept_strong_hs_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET", "s" * 48)
    monkeypatch.setenv("JWT_REFRESH_SECRET", "r" * 48)
    settings = ApiGatewaySettings()
    assert settings.jwt_secret_key == "s" * 48
    assert settings.jwt_refresh_secret_key == "r" * 48
