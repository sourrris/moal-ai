"""Backfill control-plane scopes for admin users created after 0007 migration.

Revision ID: 20260315_0009
Revises: 20260308_0008
Create Date: 2026-03-15
"""

from alembic import op

revision = "20260315_0009"
down_revision = "20260308_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE roles
        SET scopes = ARRAY(
            SELECT DISTINCT scope
            FROM unnest(
                scopes || ARRAY[
                    'control:tenants:read', 'control:tenants:write',
                    'control:config:read', 'control:config:write',
                    'control:routing:read', 'control:routing:write',
                    'control:reports:read', 'control:testlab:write'
                ]::text[]
            ) AS scope
        )
        WHERE role_name = 'admin'
          AND NOT (scopes @> ARRAY[
              'control:tenants:read', 'control:tenants:write',
              'control:config:read', 'control:config:write',
              'control:routing:read', 'control:routing:write',
              'control:reports:read', 'control:testlab:write'
          ]::text[])
        """
    )


def downgrade() -> None:
    pass  # Intentional — removing scopes is destructive
