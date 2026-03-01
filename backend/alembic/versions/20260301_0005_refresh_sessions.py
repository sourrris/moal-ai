"""Add refresh session tracking table for cookie/session token rotation.

Revision ID: 20260301_0005
Revises: 20260228_0003
Create Date: 2026-03-01 18:30:00
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260301_0005"
down_revision = "20260228_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS refresh_sessions (
            session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            username VARCHAR(120) NOT NULL,
            tenant_id VARCHAR(120) NOT NULL,
            refresh_token_hash VARCHAR(128) NOT NULL,
            issued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMPTZ NOT NULL,
            rotated_at TIMESTAMPTZ,
            revoked_at TIMESTAMPTZ,
            last_seen_at TIMESTAMPTZ,
            user_agent TEXT,
            ip_address VARCHAR(64)
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_refresh_sessions_hash_active
        ON refresh_sessions (refresh_token_hash)
        WHERE revoked_at IS NULL
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_refresh_sessions_username ON refresh_sessions (username)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_refresh_sessions_tenant ON refresh_sessions (tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_refresh_sessions_expires_at ON refresh_sessions (expires_at)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_refresh_sessions_expires_at")
    op.execute("DROP INDEX IF EXISTS idx_refresh_sessions_tenant")
    op.execute("DROP INDEX IF EXISTS idx_refresh_sessions_username")
    op.execute("DROP INDEX IF EXISTS idx_refresh_sessions_hash_active")
    op.execute("DROP TABLE IF EXISTS refresh_sessions")
