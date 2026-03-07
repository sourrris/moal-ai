"""Add tenant configuration for dynamic thresholds and connector/rule controls.

Revision ID: 20260302_0006
Revises: 20260301_0005
Create Date: 2026-03-02 23:20:00
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260302_0006"
down_revision = "20260301_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tenant_configuration (
            tenant_id VARCHAR(120) PRIMARY KEY REFERENCES tenants(tenant_id) ON DELETE CASCADE,
            anomaly_threshold DOUBLE PRECISION,
            enabled_connectors JSONB NOT NULL DEFAULT '[]'::jsonb,
            model_version VARCHAR(64),
            rule_overrides_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        INSERT INTO tenant_configuration (tenant_id, enabled_connectors)
        SELECT tenant_id, '[]'::jsonb
        FROM tenants
        ON CONFLICT (tenant_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tenant_configuration")
