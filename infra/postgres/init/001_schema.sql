CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(120) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role VARCHAR(32) NOT NULL DEFAULT 'analyst',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(120) NOT NULL,
    source VARCHAR(120) NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    features DOUBLE PRECISION[] NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'queued',
    submitted_by VARCHAR(120) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS anomaly_results (
    id BIGSERIAL PRIMARY KEY,
    event_id UUID NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
    model_name VARCHAR(120) NOT NULL,
    model_version VARCHAR(64) NOT NULL,
    anomaly_score DOUBLE PRECISION NOT NULL,
    threshold DOUBLE PRECISION NOT NULL,
    is_anomaly BOOLEAN NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS model_registry (
    id BIGSERIAL PRIMARY KEY,
    model_name VARCHAR(120) NOT NULL,
    model_version VARCHAR(64) NOT NULL,
    metadata JSONB NOT NULL,
    active BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_events_tenant_ingested ON events (tenant_id, ingested_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_status ON events (status);
CREATE INDEX IF NOT EXISTS idx_anomaly_results_event_id ON anomaly_results (event_id);
CREATE INDEX IF NOT EXISTS idx_anomaly_results_processed_at ON anomaly_results (processed_at DESC);
CREATE INDEX IF NOT EXISTS idx_model_registry_active ON model_registry (active);

INSERT INTO users (username, password_hash, role)
VALUES ('admin', crypt('admin123', gen_salt('bf')), 'admin')
ON CONFLICT (username) DO NOTHING;

CREATE TABLE IF NOT EXISTS tenants (
    tenant_id VARCHAR(120) PRIMARY KEY,
    display_name VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    tier VARCHAR(32) NOT NULL DEFAULT 'standard',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS event_sources (
    source_name VARCHAR(120) PRIMARY KEY,
    source_type VARCHAR(64) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    cadence_seconds INTEGER NOT NULL DEFAULT 3600,
    freshness_slo_seconds INTEGER,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS source_connector_state (
    source_name VARCHAR(120) PRIMARY KEY REFERENCES event_sources(source_name) ON DELETE CASCADE,
    enabled BOOLEAN,
    cursor_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    etag VARCHAR(255),
    last_modified VARCHAR(120),
    last_success_at TIMESTAMPTZ,
    last_failure_at TIMESTAMPTZ,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    backoff_until TIMESTAMPTZ,
    next_run_at TIMESTAMPTZ,
    degraded_reason TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS connector_runs (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_name VARCHAR(120) NOT NULL REFERENCES event_sources(source_name) ON DELETE CASCADE,
    status VARCHAR(32) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    fetched_records INTEGER NOT NULL DEFAULT 0,
    upserted_records INTEGER NOT NULL DEFAULT 0,
    checksum VARCHAR(255),
    cursor_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS watchlist_versions (
    id BIGSERIAL PRIMARY KEY,
    source_name VARCHAR(120) NOT NULL REFERENCES event_sources(source_name) ON DELETE CASCADE,
    version VARCHAR(120) NOT NULL,
    checksum VARCHAR(255) NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_name, version)
);

CREATE TABLE IF NOT EXISTS sanctions_entities (
    id BIGSERIAL PRIMARY KEY,
    source_name VARCHAR(120) NOT NULL,
    primary_name VARCHAR(255) NOT NULL,
    normalized_name VARCHAR(255) NOT NULL,
    entity_type VARCHAR(64),
    watchlist_id VARCHAR(120),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pep_entities (
    id BIGSERIAL PRIMARY KEY,
    source_name VARCHAR(120) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    normalized_name VARCHAR(255) NOT NULL,
    country_codes VARCHAR(8)[],
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS jurisdiction_risk (
    id BIGSERIAL PRIMARY KEY,
    source_name VARCHAR(120) NOT NULL,
    country_code VARCHAR(8) NOT NULL,
    risk_score DOUBLE PRECISION NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_name, country_code)
);

CREATE TABLE IF NOT EXISTS fx_rates (
    id BIGSERIAL PRIMARY KEY,
    source_name VARCHAR(120) NOT NULL,
    currency_pair VARCHAR(16) NOT NULL,
    rate DOUBLE PRECISION NOT NULL,
    rate_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_name, currency_pair, rate_date)
);

CREATE TABLE IF NOT EXISTS ip_intelligence (
    ip INET PRIMARY KEY,
    source_name VARCHAR(120) NOT NULL,
    country_code VARCHAR(8),
    asn VARCHAR(120),
    is_proxy BOOLEAN,
    risk_score DOUBLE PRECISION,
    raw JSONB NOT NULL DEFAULT '{}'::jsonb,
    expires_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO tenants (tenant_id, display_name, status, tier)
VALUES ('tenant-alpha', 'Tenant Alpha', 'active', 'standard')
ON CONFLICT (tenant_id) DO NOTHING;

INSERT INTO event_sources (source_name, source_type, enabled, cadence_seconds)
VALUES 
    ('ofac_sls', 'watchlist', TRUE, 3600),
    ('fatf', 'watchlist', TRUE, 86400),
    ('ecb_fx', 'fx', TRUE, 3600),
    ('mempool_bitcoin', 'transaction', TRUE, 60),
    ('abusech_ip', 'intel', TRUE, 3600)
ON CONFLICT (source_name) DO NOTHING;

