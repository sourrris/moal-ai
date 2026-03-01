"""Unit tests for auth password verification and hash upgrade behavior."""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "services" / "risk" / "api"))

from app.infrastructure.monitoring_repository import UserRepository, pwd_context


def test_verify_password_handles_modern_hash_without_upgrade() -> None:
    """A modern argon2 hash should validate and not request an upgrade."""
    stored_hash = pwd_context.hash("super-secret")

    is_valid, upgraded_hash = UserRepository.verify_password_and_upgrade_hash(
        password="super-secret",
        stored_hash=stored_hash,
    )

    assert is_valid is True
    assert upgraded_hash is None


def test_verify_password_upgrades_plaintext_legacy_values() -> None:
    """Legacy plaintext credentials should still validate and be upgraded."""
    is_valid, upgraded_hash = UserRepository.verify_password_and_upgrade_hash(
        password="legacy-password",
        stored_hash="legacy-password",
    )

    assert is_valid is True
    assert upgraded_hash is not None
    assert upgraded_hash != "legacy-password"
    assert pwd_context.verify("legacy-password", upgraded_hash)
