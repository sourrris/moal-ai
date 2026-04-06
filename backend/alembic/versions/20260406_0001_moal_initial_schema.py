"""moal-ai initial schema: users, behavior_events, anomaly_results, alerts, model_registry

Revision ID: 20260406_0001
Revises:
Create Date: 2026-04-06
"""

from alembic import op

revision = "20260406_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id BIGSERIAL PRIMARY KEY,
            username VARCHAR(120) UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role VARCHAR(32) NOT NULL DEFAULT 'admin',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        INSERT INTO users (username, password_hash, role)
        VALUES (
            'admin',
            crypt('admin123', gen_salt('bf')),
            'admin'
        )
        ON CONFLICT (username) DO NOTHING
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS behavior_events (
            event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_identifier VARCHAR(255) NOT NULL,
            event_type VARCHAR(64) NOT NULL,
            source VARCHAR(120) NOT NULL,
            source_ip INET,
            user_agent TEXT,
            geo_country VARCHAR(8),
            geo_city VARCHAR(120),
            hour_of_day SMALLINT,
            day_of_week SMALLINT,
            session_duration_seconds INTEGER,
            request_count INTEGER DEFAULT 0,
            failed_auth_count INTEGER DEFAULT 0,
            bytes_transferred BIGINT DEFAULT 0,
            endpoint VARCHAR(512),
            status_code SMALLINT,
            device_fingerprint VARCHAR(255),
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            features DOUBLE PRECISION[] NOT NULL DEFAULT '{}'::double precision[],
            occurred_at TIMESTAMPTZ NOT NULL,
            ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS anomaly_results (
            id BIGSERIAL PRIMARY KEY,
            event_id UUID NOT NULL REFERENCES behavior_events(event_id) ON DELETE CASCADE,
            anomaly_score DOUBLE PRECISION NOT NULL,
            threshold DOUBLE PRECISION NOT NULL,
            is_anomaly BOOLEAN NOT NULL,
            model_name VARCHAR(120) NOT NULL,
            model_version VARCHAR(64) NOT NULL,
            feature_vector DOUBLE PRECISION[] NOT NULL DEFAULT '{}'::double precision[],
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS alerts (
            alert_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            event_id UUID NOT NULL REFERENCES behavior_events(event_id) ON DELETE CASCADE,
            severity VARCHAR(16) NOT NULL,
            anomaly_score DOUBLE PRECISION NOT NULL,
            threshold DOUBLE PRECISION NOT NULL,
            model_name VARCHAR(120) NOT NULL,
            model_version VARCHAR(64) NOT NULL,
            state VARCHAR(32) NOT NULL DEFAULT 'open',
            user_identifier VARCHAR(255) NOT NULL,
            note TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS model_registry (
            id BIGSERIAL PRIMARY KEY,
            model_name VARCHAR(120) NOT NULL,
            model_version VARCHAR(64) NOT NULL,
            artifact_uri TEXT NOT NULL,
            feature_dim INTEGER NOT NULL,
            threshold DOUBLE PRECISION NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'active',
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            activated_at TIMESTAMPTZ,
            UNIQUE (model_name, model_version)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS model_training_runs (
            run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            model_name VARCHAR(120) NOT NULL,
            model_version VARCHAR(64),
            status VARCHAR(32) NOT NULL,
            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            finished_at TIMESTAMPTZ,
            parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
            metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
            initiated_by VARCHAR(120),
            notes TEXT
        )
        """
    )

    # Indexes
    op.execute("CREATE INDEX IF NOT EXISTS idx_behavior_events_user ON behavior_events (user_identifier, occurred_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_behavior_events_type ON behavior_events (event_type, occurred_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_behavior_events_occurred ON behavior_events (occurred_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_behavior_events_source_ip ON behavior_events (source_ip)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_anomaly_results_event ON anomaly_results (event_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_alerts_state ON alerts (state, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_alerts_user ON alerts (user_identifier, created_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS model_training_runs")
    op.execute("DROP TABLE IF EXISTS model_registry")
    op.execute("DROP TABLE IF EXISTS alerts")
    op.execute("DROP TABLE IF EXISTS anomaly_results")
    op.execute("DROP TABLE IF EXISTS behavior_events")
    op.execute("DROP TABLE IF EXISTS users")
