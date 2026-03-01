"""v2 operational foundation schema

Revision ID: 20260228_0001
Revises:
Create Date: 2026-02-28 00:00:00.000000
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260228_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id BIGSERIAL PRIMARY KEY,
            username VARCHAR(120) UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role VARCHAR(32) NOT NULL DEFAULT 'analyst',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tenants (
            tenant_id VARCHAR(120) PRIMARY KEY,
            display_name VARCHAR(255) NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'active',
            tier VARCHAR(32) NOT NULL DEFAULT 'standard',
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS roles (
            role_name VARCHAR(64) PRIMARY KEY,
            description TEXT NOT NULL,
            scopes TEXT[] NOT NULL DEFAULT '{}'::text[]
        )
        """
    )
    op.execute(
        """
        INSERT INTO roles (role_name, description, scopes)
        VALUES
            ('admin', 'Tenant administrator', ARRAY['events:write','events:read','alerts:write','alerts:read','models:read','models:write','connectors:read']),
            ('analyst', 'Fraud analyst', ARRAY['events:read','alerts:read','alerts:write','models:read']),
            ('viewer', 'Read-only operator', ARRAY['events:read','alerts:read','models:read'])
        ON CONFLICT (role_name) DO NOTHING
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_tenant_roles (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            tenant_id VARCHAR(120) NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
            role_name VARCHAR(64) NOT NULL REFERENCES roles(role_name) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (user_id, tenant_id, role_name)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tenant_keys (
            key_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id VARCHAR(120) NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
            key_type VARCHAR(32) NOT NULL,
            key_hash TEXT NOT NULL,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            rotated_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS event_sources (
            source_id BIGSERIAL PRIMARY KEY,
            source_name VARCHAR(120) UNIQUE NOT NULL,
            source_type VARCHAR(64) NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            cadence_seconds INTEGER NOT NULL DEFAULT 3600,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS connector_runs (
            run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source_name VARCHAR(120) NOT NULL,
            status VARCHAR(32) NOT NULL,
            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            finished_at TIMESTAMPTZ,
            fetched_records INTEGER NOT NULL DEFAULT 0,
            upserted_records INTEGER NOT NULL DEFAULT 0,
            checksum TEXT,
            cursor_state JSONB NOT NULL DEFAULT '{}'::jsonb,
            details JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS connector_errors (
            id BIGSERIAL PRIMARY KEY,
            run_id UUID REFERENCES connector_runs(run_id) ON DELETE SET NULL,
            source_name VARCHAR(120) NOT NULL,
            error_code VARCHAR(64),
            message TEXT NOT NULL,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS watchlist_versions (
            id BIGSERIAL PRIMARY KEY,
            source_name VARCHAR(120) NOT NULL,
            version VARCHAR(120) NOT NULL,
            content_hash TEXT NOT NULL,
            published_at TIMESTAMPTZ,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            UNIQUE (source_name, version)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS events_v2 (
            event_id UUID NOT NULL DEFAULT gen_random_uuid(),
            tenant_id VARCHAR(120) NOT NULL,
            idempotency_key VARCHAR(128) NOT NULL,
            source VARCHAR(120) NOT NULL,
            event_type VARCHAR(120) NOT NULL,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            transaction_amount NUMERIC(18,6) NOT NULL,
            transaction_currency VARCHAR(12) NOT NULL,
            source_ip INET,
            source_country VARCHAR(8),
            destination_country VARCHAR(8),
            card_bin VARCHAR(12),
            card_last4 VARCHAR(4),
            user_email_hash VARCHAR(128),
            occurred_at TIMESTAMPTZ NOT NULL,
            ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            status VARCHAR(32) NOT NULL DEFAULT 'queued',
            submitted_by VARCHAR(120) NOT NULL,
            PRIMARY KEY (tenant_id, ingested_at, event_id),
            FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE
        ) PARTITION BY RANGE (ingested_at)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS event_idempotency_keys (
            tenant_id VARCHAR(120) NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
            idempotency_key VARCHAR(128) NOT NULL,
            event_id UUID NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (tenant_id, idempotency_key)
        )
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION ensure_events_v2_daily_partitions(
            from_date DATE,
            to_date DATE,
            hash_partitions INTEGER DEFAULT 8
        ) RETURNS VOID AS $$
        DECLARE
            d DATE;
            partition_name TEXT;
            subpartition_name TEXT;
            part_start TIMESTAMPTZ;
            part_end TIMESTAMPTZ;
            i INTEGER;
        BEGIN
            d := from_date;
            WHILE d <= to_date LOOP
                partition_name := format('events_v2_%s', to_char(d, 'YYYYMMDD'));
                part_start := d::timestamptz;
                part_end := (d + INTERVAL '1 day')::timestamptz;

                EXECUTE format(
                    'CREATE TABLE IF NOT EXISTS %I PARTITION OF events_v2 FOR VALUES FROM (%L) TO (%L) PARTITION BY HASH (tenant_id)',
                    partition_name,
                    part_start,
                    part_end
                );

                i := 0;
                WHILE i < hash_partitions LOOP
                    subpartition_name := format('%s_p%s', partition_name, i);
                    EXECUTE format(
                        'CREATE TABLE IF NOT EXISTS %I PARTITION OF %I FOR VALUES WITH (MODULUS %s, REMAINDER %s)',
                        subpartition_name,
                        partition_name,
                        hash_partitions,
                        i
                    );
                    i := i + 1;
                END LOOP;

                d := d + INTERVAL '1 day';
            END LOOP;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute("SELECT ensure_events_v2_daily_partitions(CURRENT_DATE - 1, CURRENT_DATE + 7, 8)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS event_enrichments (
            id BIGSERIAL PRIMARY KEY,
            tenant_id VARCHAR(120) NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
            event_id UUID NOT NULL,
            sources JSONB NOT NULL DEFAULT '[]'::jsonb,
            enrichment_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            match_confidence DOUBLE PRECISION,
            enrichment_latency_ms INTEGER,
            enriched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (tenant_id, event_id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS risk_decisions (
            decision_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id VARCHAR(120) NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
            event_id UUID NOT NULL,
            risk_score DOUBLE PRECISION NOT NULL,
            risk_level VARCHAR(16) NOT NULL,
            reasons TEXT[] NOT NULL DEFAULT '{}'::text[],
            rule_hits TEXT[] NOT NULL DEFAULT '{}'::text[],
            model_name VARCHAR(120) NOT NULL,
            model_version VARCHAR(64) NOT NULL,
            ml_anomaly_score DOUBLE PRECISION,
            ml_threshold DOUBLE PRECISION,
            decision_latency_ms INTEGER,
            feature_vector DOUBLE PRECISION[] NOT NULL DEFAULT '{}'::double precision[],
            decision_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (tenant_id, event_id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS alerts_v2 (
            alert_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id VARCHAR(120) NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
            event_id UUID NOT NULL,
            decision_id UUID REFERENCES risk_decisions(decision_id) ON DELETE SET NULL,
            state VARCHAR(32) NOT NULL DEFAULT 'open',
            severity VARCHAR(16) NOT NULL,
            risk_score DOUBLE PRECISION NOT NULL,
            reasons TEXT[] NOT NULL DEFAULT '{}'::text[],
            assigned_to VARCHAR(120),
            opened_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            acknowledged_at TIMESTAMPTZ,
            resolved_at TIMESTAMPTZ
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS sanctions_entities (
            id BIGSERIAL PRIMARY KEY,
            source_name VARCHAR(120) NOT NULL,
            entity_id TEXT NOT NULL,
            primary_name TEXT NOT NULL,
            aliases TEXT[] NOT NULL DEFAULT '{}'::text[],
            countries TEXT[] NOT NULL DEFAULT '{}'::text[],
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            first_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (source_name, entity_id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS pep_entities (
            id BIGSERIAL PRIMARY KEY,
            source_name VARCHAR(120) NOT NULL,
            entity_id TEXT NOT NULL,
            full_name TEXT NOT NULL,
            aliases TEXT[] NOT NULL DEFAULT '{}'::text[],
            jurisdictions TEXT[] NOT NULL DEFAULT '{}'::text[],
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            first_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (source_name, entity_id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS jurisdiction_risk_scores (
            source_name VARCHAR(120) NOT NULL,
            jurisdiction_code VARCHAR(8) NOT NULL,
            risk_score DOUBLE PRECISION NOT NULL,
            risk_level VARCHAR(16) NOT NULL,
            details JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (source_name, jurisdiction_code)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ip_intelligence_cache (
            ip INET PRIMARY KEY,
            source_name VARCHAR(120) NOT NULL,
            country_code VARCHAR(8),
            asn VARCHAR(32),
            is_proxy BOOLEAN,
            risk_score DOUBLE PRECISION,
            raw JSONB NOT NULL DEFAULT '{}'::jsonb,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMPTZ NOT NULL
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS bin_intelligence_cache (
            bin VARCHAR(12) PRIMARY KEY,
            source_name VARCHAR(120) NOT NULL,
            country_code VARCHAR(8),
            issuer TEXT,
            card_type VARCHAR(64),
            card_brand VARCHAR(64),
            prepaid BOOLEAN,
            raw JSONB NOT NULL DEFAULT '{}'::jsonb,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMPTZ NOT NULL
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS fx_rates (
            source_name VARCHAR(120) NOT NULL,
            base_currency VARCHAR(12) NOT NULL,
            quote_currency VARCHAR(12) NOT NULL,
            rate_date DATE NOT NULL,
            rate NUMERIC(20,10) NOT NULL,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (source_name, base_currency, quote_currency, rate_date)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS model_registry_v2 (
            id BIGSERIAL PRIMARY KEY,
            model_name VARCHAR(120) NOT NULL,
            model_version VARCHAR(64) NOT NULL,
            artifact_uri TEXT NOT NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            feature_dim INTEGER NOT NULL,
            threshold DOUBLE PRECISION NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'active',
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

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS feature_stats (
            id BIGSERIAL PRIMARY KEY,
            tenant_id VARCHAR(120),
            model_name VARCHAR(120) NOT NULL,
            model_version VARCHAR(64) NOT NULL,
            feature_name VARCHAR(120) NOT NULL,
            period_start TIMESTAMPTZ NOT NULL,
            period_end TIMESTAMPTZ NOT NULL,
            mean DOUBLE PRECISION,
            stddev DOUBLE PRECISION,
            p50 DOUBLE PRECISION,
            p95 DOUBLE PRECISION,
            null_rate DOUBLE PRECISION,
            sample_count BIGINT NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS drift_snapshots (
            snapshot_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id VARCHAR(120),
            model_name VARCHAR(120) NOT NULL,
            model_version VARCHAR(64) NOT NULL,
            drift_score DOUBLE PRECISION NOT NULL,
            drift_status VARCHAR(32) NOT NULL,
            details JSONB NOT NULL DEFAULT '{}'::jsonb,
            observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS metrics_1m (
            tenant_id VARCHAR(120) NOT NULL,
            bucket TIMESTAMPTZ NOT NULL,
            total_events BIGINT NOT NULL DEFAULT 0,
            total_alerts BIGINT NOT NULL DEFAULT 0,
            avg_risk_score DOUBLE PRECISION,
            p95_decision_latency_ms INTEGER,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (tenant_id, bucket)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS metrics_1h (
            tenant_id VARCHAR(120) NOT NULL,
            bucket TIMESTAMPTZ NOT NULL,
            total_events BIGINT NOT NULL DEFAULT 0,
            total_alerts BIGINT NOT NULL DEFAULT 0,
            avg_risk_score DOUBLE PRECISION,
            p95_decision_latency_ms INTEGER,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (tenant_id, bucket)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tenant_health_snapshots (
            snapshot_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id VARCHAR(120) NOT NULL,
            window_minutes INTEGER NOT NULL,
            availability DOUBLE PRECISION,
            error_rate DOUBLE PRECISION,
            event_lag_seconds DOUBLE PRECISION,
            stream_delay_seconds DOUBLE PRECISION,
            status VARCHAR(32) NOT NULL,
            details JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS decision_audit_log (
            id BIGSERIAL PRIMARY KEY,
            tenant_id VARCHAR(120) NOT NULL,
            event_id UUID,
            decision_id UUID,
            actor_type VARCHAR(32) NOT NULL,
            actor_id VARCHAR(120) NOT NULL,
            action VARCHAR(64) NOT NULL,
            before_state JSONB NOT NULL DEFAULT '{}'::jsonb,
            after_state JSONB NOT NULL DEFAULT '{}'::jsonb,
            reason TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS data_access_audit_log (
            id BIGSERIAL PRIMARY KEY,
            tenant_id VARCHAR(120) NOT NULL,
            subject VARCHAR(120) NOT NULL,
            action VARCHAR(64) NOT NULL,
            resource TEXT NOT NULL,
            client_ip INET,
            user_agent TEXT,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS retention_jobs (
            job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id VARCHAR(120),
            policy_name VARCHAR(64) NOT NULL,
            status VARCHAR(32) NOT NULL,
            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            finished_at TIMESTAMPTZ,
            records_processed BIGINT NOT NULL DEFAULT 0,
            details JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )

    # Query-performance indexes for scale workloads.
    op.execute("CREATE INDEX IF NOT EXISTS idx_events_v2_brin_ingested ON events_v2 USING BRIN (ingested_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_events_v2_tenant_occurred ON events_v2 (tenant_id, occurred_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_events_v2_status_hot ON events_v2 (tenant_id, ingested_at DESC) WHERE status IN ('queued','failed','anomaly')")
    op.execute("CREATE INDEX IF NOT EXISTS idx_events_v2_payload_gin ON events_v2 USING GIN (payload jsonb_path_ops)")

    op.execute("CREATE INDEX IF NOT EXISTS idx_risk_decisions_brin_created ON risk_decisions USING BRIN (created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_risk_decisions_tenant_created ON risk_decisions (tenant_id, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_risk_decisions_payload_gin ON risk_decisions USING GIN (decision_payload jsonb_path_ops)")

    op.execute("CREATE INDEX IF NOT EXISTS idx_alerts_v2_open ON alerts_v2 (tenant_id, opened_at DESC) WHERE state = 'open'")
    op.execute("CREATE INDEX IF NOT EXISTS idx_alerts_v2_state ON alerts_v2 (tenant_id, state, opened_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_alerts_v2_event ON alerts_v2 (tenant_id, event_id)")

    op.execute("CREATE INDEX IF NOT EXISTS idx_connector_runs_source_time ON connector_runs (source_name, started_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_connector_errors_time ON connector_errors (source_name, occurred_at DESC)")

    op.execute("CREATE INDEX IF NOT EXISTS idx_sanctions_primary_name_trgm ON sanctions_entities USING GIN (primary_name gin_trgm_ops)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_pep_full_name_trgm ON pep_entities USING GIN (full_name gin_trgm_ops)")

    op.execute("CREATE INDEX IF NOT EXISTS idx_feature_stats_tenant_period ON feature_stats (tenant_id, period_end DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_drift_snapshots_tenant_observed ON drift_snapshots (tenant_id, observed_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_metrics_1m_bucket ON metrics_1m (bucket DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_metrics_1h_bucket ON metrics_1h (bucket DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tenant_health_tenant_created ON tenant_health_snapshots (tenant_id, created_at DESC)")

    op.execute(
        """
        CREATE OR REPLACE FUNCTION app_current_tenant() RETURNS TEXT AS $$
            SELECT NULLIF(current_setting('app.current_tenant', true), '')
        $$ LANGUAGE SQL STABLE
        """
    )

    for table_name in [
        "events_v2",
        "event_enrichments",
        "risk_decisions",
        "alerts_v2",
        "metrics_1m",
        "metrics_1h",
        "tenant_health_snapshots",
        "feature_stats",
        "decision_audit_log",
        "data_access_audit_log",
    ]:
        op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")

    op.execute(
        """
        CREATE POLICY tenant_isolation_events_v2 ON events_v2
        USING (tenant_id = app_current_tenant())
        WITH CHECK (tenant_id = app_current_tenant())
        """
    )
    op.execute(
        """
        CREATE POLICY tenant_isolation_event_enrichments ON event_enrichments
        USING (tenant_id = app_current_tenant())
        WITH CHECK (tenant_id = app_current_tenant())
        """
    )
    op.execute(
        """
        CREATE POLICY tenant_isolation_risk_decisions ON risk_decisions
        USING (tenant_id = app_current_tenant())
        WITH CHECK (tenant_id = app_current_tenant())
        """
    )
    op.execute(
        """
        CREATE POLICY tenant_isolation_alerts_v2 ON alerts_v2
        USING (tenant_id = app_current_tenant())
        WITH CHECK (tenant_id = app_current_tenant())
        """
    )
    op.execute(
        """
        CREATE POLICY tenant_isolation_metrics_1m ON metrics_1m
        USING (tenant_id = app_current_tenant())
        WITH CHECK (tenant_id = app_current_tenant())
        """
    )
    op.execute(
        """
        CREATE POLICY tenant_isolation_metrics_1h ON metrics_1h
        USING (tenant_id = app_current_tenant())
        WITH CHECK (tenant_id = app_current_tenant())
        """
    )
    op.execute(
        """
        CREATE POLICY tenant_isolation_tenant_health_snapshots ON tenant_health_snapshots
        USING (tenant_id = app_current_tenant())
        WITH CHECK (tenant_id = app_current_tenant())
        """
    )
    op.execute(
        """
        CREATE POLICY tenant_isolation_feature_stats ON feature_stats
        USING (tenant_id IS NULL OR tenant_id = app_current_tenant())
        WITH CHECK (tenant_id IS NULL OR tenant_id = app_current_tenant())
        """
    )
    op.execute(
        """
        CREATE POLICY tenant_isolation_decision_audit_log ON decision_audit_log
        USING (tenant_id = app_current_tenant())
        WITH CHECK (tenant_id = app_current_tenant())
        """
    )
    op.execute(
        """
        CREATE POLICY tenant_isolation_data_access_audit_log ON data_access_audit_log
        USING (tenant_id = app_current_tenant())
        WITH CHECK (tenant_id = app_current_tenant())
        """
    )

    op.execute(
        """
        INSERT INTO tenants (tenant_id, display_name, status, tier)
        VALUES ('tenant-alpha', 'Tenant Alpha', 'active', 'standard')
        ON CONFLICT (tenant_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO tenants (tenant_id, display_name, status, tier)
        VALUES ('tenant-beta', 'Tenant Beta', 'active', 'standard')
        ON CONFLICT (tenant_id) DO NOTHING
        """
    )

    op.execute(
        """
        INSERT INTO event_sources (source_name, source_type, enabled, cadence_seconds)
        VALUES
          ('ofac_sls', 'sanctions', TRUE, 900),
          ('fatf', 'jurisdiction_risk', TRUE, 86400),
          ('ecb_fx', 'fx_rates', TRUE, 86400)
        ON CONFLICT (source_name) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO user_tenant_roles (user_id, tenant_id, role_name)
        SELECT
            u.id,
            'tenant-alpha',
            CASE
                WHEN u.role IN ('admin', 'analyst', 'viewer') THEN u.role
                ELSE 'analyst'
            END
        FROM users u
        ON CONFLICT (user_id, tenant_id, role_name) DO NOTHING
        """
    )


def downgrade() -> None:
    for policy_name, table_name in [
        ("tenant_isolation_data_access_audit_log", "data_access_audit_log"),
        ("tenant_isolation_decision_audit_log", "decision_audit_log"),
        ("tenant_isolation_feature_stats", "feature_stats"),
        ("tenant_isolation_tenant_health_snapshots", "tenant_health_snapshots"),
        ("tenant_isolation_metrics_1h", "metrics_1h"),
        ("tenant_isolation_metrics_1m", "metrics_1m"),
        ("tenant_isolation_alerts_v2", "alerts_v2"),
        ("tenant_isolation_risk_decisions", "risk_decisions"),
        ("tenant_isolation_event_enrichments", "event_enrichments"),
        ("tenant_isolation_events_v2", "events_v2"),
    ]:
        op.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table_name}")

    op.execute("DROP FUNCTION IF EXISTS app_current_tenant")
    op.execute("DROP FUNCTION IF EXISTS ensure_events_v2_daily_partitions")

    op.execute("DROP TABLE IF EXISTS retention_jobs")
    op.execute("DROP TABLE IF EXISTS data_access_audit_log")
    op.execute("DROP TABLE IF EXISTS decision_audit_log")
    op.execute("DROP TABLE IF EXISTS tenant_health_snapshots")
    op.execute("DROP TABLE IF EXISTS metrics_1h")
    op.execute("DROP TABLE IF EXISTS metrics_1m")
    op.execute("DROP TABLE IF EXISTS drift_snapshots")
    op.execute("DROP TABLE IF EXISTS feature_stats")
    op.execute("DROP TABLE IF EXISTS model_training_runs")
    op.execute("DROP TABLE IF EXISTS model_registry_v2")
    op.execute("DROP TABLE IF EXISTS fx_rates")
    op.execute("DROP TABLE IF EXISTS bin_intelligence_cache")
    op.execute("DROP TABLE IF EXISTS ip_intelligence_cache")
    op.execute("DROP TABLE IF EXISTS jurisdiction_risk_scores")
    op.execute("DROP TABLE IF EXISTS pep_entities")
    op.execute("DROP TABLE IF EXISTS sanctions_entities")
    op.execute("DROP TABLE IF EXISTS alerts_v2")
    op.execute("DROP TABLE IF EXISTS risk_decisions")
    op.execute("DROP TABLE IF EXISTS event_enrichments")
    op.execute("DROP TABLE IF EXISTS event_idempotency_keys")
    op.execute("DROP TABLE IF EXISTS events_v2")
    op.execute("DROP TABLE IF EXISTS watchlist_versions")
    op.execute("DROP TABLE IF EXISTS connector_errors")
    op.execute("DROP TABLE IF EXISTS connector_runs")
    op.execute("DROP TABLE IF EXISTS event_sources")
    op.execute("DROP TABLE IF EXISTS tenant_keys")
    op.execute("DROP TABLE IF EXISTS user_tenant_roles")
    op.execute("DROP TABLE IF EXISTS roles")
    op.execute("DROP TABLE IF EXISTS tenants")
