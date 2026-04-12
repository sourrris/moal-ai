"""Add user_baselines table for per-user behavioral context.

Revision ID: 20260412_0002
Revises: 20260406_0001
Create Date: 2026-04-12
"""

from alembic import op

revision = "20260412_0002"
down_revision = "20260406_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_baselines (
            user_identifier VARCHAR(255) PRIMARY KEY,

            -- Volume
            total_events BIGINT NOT NULL DEFAULT 0,
            total_anomalies BIGINT NOT NULL DEFAULT 0,

            -- Temporal pattern: count of events per hour bucket (24-element array)
            hourly_counts BIGINT[] NOT NULL DEFAULT '{0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0}'::bigint[],

            -- Known context sets (JSONB maps: value -> count)
            known_ips JSONB NOT NULL DEFAULT '{}'::jsonb,
            known_devices JSONB NOT NULL DEFAULT '{}'::jsonb,
            known_countries JSONB NOT NULL DEFAULT '{}'::jsonb,

            -- Rolling averages
            avg_session_duration DOUBLE PRECISION NOT NULL DEFAULT 0.0,
            avg_request_rate DOUBLE PRECISION NOT NULL DEFAULT 0.0,
            avg_failed_auth_ratio DOUBLE PRECISION NOT NULL DEFAULT 0.0,

            -- Recency
            last_event_at TIMESTAMPTZ,
            events_last_hour BIGINT NOT NULL DEFAULT 0,
            events_last_hour_window_start TIMESTAMPTZ,

            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_baselines_updated ON user_baselines (updated_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_baselines")
