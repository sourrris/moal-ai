"""Add tenant onboarding surfaces for domains and API keys.

Revision ID: 20260308_0008
Revises: 20260302_0007
Create Date: 2026-03-08 19:30:00
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260308_0008"
down_revision = "20260302_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tenant_domains (
            domain_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id VARCHAR(120) NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
            hostname VARCHAR(255) NOT NULL,
            created_by VARCHAR(120),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (hostname)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_tenant_domains_tenant_created
        ON tenant_domains (tenant_id, created_at DESC)
        """
    )

    op.execute(
        """
        ALTER TABLE tenant_keys
        ADD COLUMN IF NOT EXISTS name VARCHAR(255) NOT NULL DEFAULT 'Ingest key'
        """
    )
    op.execute(
        """
        ALTER TABLE tenant_keys
        ADD COLUMN IF NOT EXISTS key_prefix VARCHAR(64)
        """
    )
    op.execute(
        """
        ALTER TABLE tenant_keys
        ADD COLUMN IF NOT EXISTS scopes TEXT[] NOT NULL DEFAULT ARRAY['events:write']::text[]
        """
    )
    op.execute(
        """
        ALTER TABLE tenant_keys
        ADD COLUMN IF NOT EXISTS domain_id UUID REFERENCES tenant_domains(domain_id) ON DELETE SET NULL
        """
    )
    op.execute(
        """
        ALTER TABLE tenant_keys
        ADD COLUMN IF NOT EXISTS created_by VARCHAR(120)
        """
    )
    op.execute(
        """
        ALTER TABLE tenant_keys
        ADD COLUMN IF NOT EXISTS last_used_at TIMESTAMPTZ
        """
    )
    op.execute(
        """
        ALTER TABLE tenant_keys
        ADD COLUMN IF NOT EXISTS revoked_at TIMESTAMPTZ
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_tenant_keys_tenant_active
        ON tenant_keys (tenant_id, active, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_tenant_keys_prefix
        ON tenant_keys (key_prefix)
        WHERE key_prefix IS NOT NULL
        """
    )

    op.execute(
        """
        UPDATE tenant_keys
        SET
            name = COALESCE(NULLIF(name, ''), 'Ingest key'),
            key_prefix = COALESCE(key_prefix, 'legacy_' || SUBSTRING(REPLACE(key_id::text, '-', '') FROM 1 FOR 8)),
            scopes = CASE
                WHEN COALESCE(array_length(scopes, 1), 0) = 0 THEN ARRAY['events:write']::text[]
                ELSE scopes
            END
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_tenant_keys_prefix")
    op.execute("DROP INDEX IF EXISTS idx_tenant_keys_tenant_active")
    op.execute("ALTER TABLE tenant_keys DROP COLUMN IF EXISTS revoked_at")
    op.execute("ALTER TABLE tenant_keys DROP COLUMN IF EXISTS last_used_at")
    op.execute("ALTER TABLE tenant_keys DROP COLUMN IF EXISTS created_by")
    op.execute("ALTER TABLE tenant_keys DROP COLUMN IF EXISTS domain_id")
    op.execute("ALTER TABLE tenant_keys DROP COLUMN IF EXISTS scopes")
    op.execute("ALTER TABLE tenant_keys DROP COLUMN IF EXISTS key_prefix")
    op.execute("ALTER TABLE tenant_keys DROP COLUMN IF EXISTS name")

    op.execute("DROP INDEX IF EXISTS idx_tenant_domains_tenant_created")
    op.execute("DROP TABLE IF EXISTS tenant_domains")
