"""connector state and source health metadata

Revision ID: 20260228_0002
Revises: 20260228_0001
Create Date: 2026-02-28 23:15:00.000000
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260228_0002"
down_revision = "20260228_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE event_sources
        ADD COLUMN IF NOT EXISTS freshness_slo_seconds INTEGER NOT NULL DEFAULT 3600
        """
    )
    op.execute(
        """
        ALTER TABLE event_sources
        ADD COLUMN IF NOT EXISTS required_env VARCHAR(128)
        """
    )

    op.execute(
        """
        INSERT INTO event_sources (source_name, source_type, enabled, cadence_seconds, freshness_slo_seconds, required_env)
        VALUES
          ('maxmind_geolite2', 'ip_intelligence', TRUE, 86400, 108000, 'MAXMIND_LICENSE_KEY'),
          ('hibp', 'breach_intelligence', FALSE, 86400, 172800, 'HIBP_API_KEY')
        ON CONFLICT (source_name) DO UPDATE SET
          source_type = EXCLUDED.source_type,
          freshness_slo_seconds = EXCLUDED.freshness_slo_seconds,
          required_env = EXCLUDED.required_env
        """
    )
    op.execute(
        """
        UPDATE event_sources
        SET freshness_slo_seconds = CASE source_name
            WHEN 'ofac_sls' THEN 1200
            WHEN 'opensanctions' THEN 7200
            WHEN 'fatf' THEN 93600
            WHEN 'ipinfo' THEN 600
            WHEN 'binlist' THEN 600
            WHEN 'ecb_fx' THEN 93600
            WHEN 'maxmind_geolite2' THEN 108000
            WHEN 'hibp' THEN 172800
            ELSE GREATEST(cadence_seconds * 2, 600)
        END
        """
    )
    op.execute(
        """
        UPDATE event_sources
        SET required_env = CASE source_name
            WHEN 'opensanctions' THEN 'OPENSANCTIONS_API_KEY'
            WHEN 'ipinfo' THEN 'IPINFO_TOKEN'
            WHEN 'binlist' THEN NULL
            WHEN 'hibp' THEN 'HIBP_API_KEY'
            WHEN 'maxmind_geolite2' THEN 'MAXMIND_LICENSE_KEY'
            ELSE required_env
        END
        """
    )
    op.execute(
        """
        UPDATE event_sources
        SET enabled = CASE source_name
            WHEN 'opensanctions' THEN FALSE
            WHEN 'ipinfo' THEN FALSE
            WHEN 'binlist' THEN FALSE
            WHEN 'hibp' THEN FALSE
            ELSE enabled
        END
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS source_connector_state (
            source_name VARCHAR(120) PRIMARY KEY REFERENCES event_sources(source_name) ON DELETE CASCADE,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            cursor_state JSONB NOT NULL DEFAULT '{}'::jsonb,
            etag TEXT,
            last_modified TEXT,
            last_success_at TIMESTAMPTZ,
            last_failure_at TIMESTAMPTZ,
            consecutive_failures INTEGER NOT NULL DEFAULT 0,
            backoff_until TIMESTAMPTZ,
            next_run_at TIMESTAMPTZ,
            degraded_reason TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        INSERT INTO source_connector_state (source_name, enabled, next_run_at)
        SELECT source_name, enabled, NOW()
        FROM event_sources
        ON CONFLICT (source_name) DO UPDATE SET
            enabled = EXCLUDED.enabled,
            updated_at = NOW()
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_source_connector_state_next_run
        ON source_connector_state (next_run_at)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_alerts_v2_tenant_event
        ON alerts_v2 (tenant_id, event_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_connector_runs_source_started_desc
        ON connector_runs (source_name, started_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_connector_errors_source_occurred_desc
        ON connector_errors (source_name, occurred_at DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_connector_errors_source_occurred_desc")
    op.execute("DROP INDEX IF EXISTS idx_connector_runs_source_started_desc")
    op.execute("DROP INDEX IF EXISTS uq_alerts_v2_tenant_event")
    op.execute("DROP INDEX IF EXISTS idx_source_connector_state_next_run")
    op.execute("DROP TABLE IF EXISTS source_connector_state")
    op.execute("ALTER TABLE event_sources DROP COLUMN IF EXISTS required_env")
    op.execute("ALTER TABLE event_sources DROP COLUMN IF EXISTS freshness_slo_seconds")
    op.execute("DELETE FROM event_sources WHERE source_name IN ('maxmind_geolite2', 'hibp')")
