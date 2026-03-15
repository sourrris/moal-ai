"""Control plane console foundation schema.

Revision ID: 20260302_0007
Revises: 20260302_0006
Create Date: 2026-03-02 23:59:00
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260302_0007"
down_revision = "20260302_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE tenant_configuration
        ADD COLUMN IF NOT EXISTS version BIGINT NOT NULL DEFAULT 1
        """
    )
    op.execute("UPDATE tenant_configuration SET version = 1 WHERE version IS NULL")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS control_alert_destinations (
            destination_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id VARCHAR(120) NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
            channel VARCHAR(32) NOT NULL,
            name VARCHAR(255) NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            verification_status VARCHAR(32) NOT NULL DEFAULT 'pending',
            last_tested_at TIMESTAMPTZ,
            created_by VARCHAR(120),
            updated_by VARCHAR(120),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_control_alert_destinations_tenant_channel
        ON control_alert_destinations (tenant_id, channel)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS control_alert_routing_policy (
            tenant_id VARCHAR(120) PRIMARY KEY REFERENCES tenants(tenant_id) ON DELETE CASCADE,
            policy_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_by VARCHAR(120),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS control_alert_delivery_logs (
            delivery_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id VARCHAR(120) NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
            destination_id UUID REFERENCES control_alert_destinations(destination_id) ON DELETE SET NULL,
            channel VARCHAR(32) NOT NULL,
            alert_key VARCHAR(180) NOT NULL,
            event_id UUID,
            status VARCHAR(32) NOT NULL,
            attempt_no INTEGER NOT NULL DEFAULT 1,
            response_code INTEGER,
            response_body TEXT,
            error_message TEXT,
            payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            is_test BOOLEAN NOT NULL DEFAULT FALSE,
            attempted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            delivered_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_control_alert_delivery_logs_tenant_attempted
        ON control_alert_delivery_logs (tenant_id, attempted_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_control_alert_delivery_logs_alert_key
        ON control_alert_delivery_logs (alert_key)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS control_test_datasets (
            dataset_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id VARCHAR(120) NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL,
            source_type VARCHAR(32) NOT NULL DEFAULT 'json',
            payload_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            row_count INTEGER NOT NULL DEFAULT 0,
            uploaded_by VARCHAR(120),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_control_test_datasets_tenant_created
        ON control_test_datasets (tenant_id, created_at DESC)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS control_test_runs (
            run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id VARCHAR(120) NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
            dataset_id UUID REFERENCES control_test_datasets(dataset_id) ON DELETE SET NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'queued',
            created_by VARCHAR(120),
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ,
            summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_control_test_runs_tenant_created
        ON control_test_runs (tenant_id, created_at DESC)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS control_test_run_results (
            id BIGSERIAL PRIMARY KEY,
            run_id UUID NOT NULL REFERENCES control_test_runs(run_id) ON DELETE CASCADE,
            event_id UUID,
            ingest_status VARCHAR(32),
            queued BOOLEAN,
            decision_found BOOLEAN NOT NULL DEFAULT FALSE,
            risk_level VARCHAR(32),
            risk_score DOUBLE PRECISION,
            alert_found BOOLEAN NOT NULL DEFAULT FALSE,
            details JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_control_test_run_results_run
        ON control_test_run_results (run_id, id)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS control_config_audit_log (
            id BIGSERIAL PRIMARY KEY,
            tenant_id VARCHAR(120) REFERENCES tenants(tenant_id) ON DELETE SET NULL,
            actor VARCHAR(120) NOT NULL,
            action VARCHAR(120) NOT NULL,
            resource_type VARCHAR(120) NOT NULL,
            resource_id VARCHAR(180),
            before_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            after_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_control_config_audit_tenant_created
        ON control_config_audit_log (tenant_id, created_at DESC)
        """
    )

    op.execute(
        """
        UPDATE roles
        SET scopes = ARRAY(
            SELECT DISTINCT scope
            FROM unnest(
                scopes
                || ARRAY[
                    'control:tenants:read',
                    'control:tenants:write',
                    'control:config:read',
                    'control:config:write',
                    'control:routing:read',
                    'control:routing:write',
                    'control:reports:read',
                    'control:testlab:write'
                ]::text[]
            ) AS scope
        )
        WHERE role_name = 'admin'
        """
    )



def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_control_config_audit_tenant_created")
    op.execute("DROP TABLE IF EXISTS control_config_audit_log")

    op.execute("DROP INDEX IF EXISTS idx_control_test_run_results_run")
    op.execute("DROP TABLE IF EXISTS control_test_run_results")

    op.execute("DROP INDEX IF EXISTS idx_control_test_runs_tenant_created")
    op.execute("DROP TABLE IF EXISTS control_test_runs")

    op.execute("DROP INDEX IF EXISTS idx_control_test_datasets_tenant_created")
    op.execute("DROP TABLE IF EXISTS control_test_datasets")

    op.execute("DROP INDEX IF EXISTS idx_control_alert_delivery_logs_alert_key")
    op.execute("DROP INDEX IF EXISTS idx_control_alert_delivery_logs_tenant_attempted")
    op.execute("DROP TABLE IF EXISTS control_alert_delivery_logs")

    op.execute("DROP TABLE IF EXISTS control_alert_routing_policy")

    op.execute("DROP INDEX IF EXISTS idx_control_alert_destinations_tenant_channel")
    op.execute("DROP TABLE IF EXISTS control_alert_destinations")

    op.execute("ALTER TABLE tenant_configuration DROP COLUMN IF EXISTS version")
