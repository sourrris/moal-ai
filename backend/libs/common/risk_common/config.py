from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseServiceSettings(BaseSettings):
    service_name: str = "unknown-service"
    environment: str = "development"
    log_level: str = "INFO"

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    rabbitmq_url: str = Field(
        default="amqp://guest:guest@rabbitmq:5672/",
        validation_alias=AliasChoices("RABBITMQ_URL", "rabbitmq_url"),
    )
    rabbitmq_events_exchange: str = "risk.events.exchange"
    rabbitmq_events_routing_key: str = "risk.events.ingested"
    rabbitmq_events_queue: str = "risk.events.queue"
    rabbitmq_events_v2_routing_key: str = "risk.events.v2.ingested"
    rabbitmq_events_v2_queue: str = "risk.events.v2.queue"
    rabbitmq_events_dlq: str = "risk.events.dlq"
    rabbitmq_alerts_exchange: str = "risk.alerts.exchange"
    rabbitmq_alerts_routing_key: str = "risk.alerts.raised"
    rabbitmq_alerts_queue: str = "risk.alerts.queue"
    rabbitmq_dlx_exchange: str = "risk.deadletter.exchange"
    rabbitmq_metrics_exchange: str = "risk.metrics.exchange"
    rabbitmq_metrics_routing_key: str = "risk.metrics.updated"
    rabbitmq_metrics_queue: str = "risk.metrics.queue"
    rabbitmq_reference_exchange: str = "risk.reference.exchange"
    rabbitmq_reference_routing_key: str = "risk.reference.updated"
    rabbitmq_reference_queue: str = "risk.reference.queue"
    rabbitmq_queue_type: str = "classic"

    redis_url: str = Field(
        default="redis://redis:6379/0",
        validation_alias=AliasChoices("REDIS_URL", "redis_url"),
    )
    redis_alert_channel: str = "risk.alerts.live"
    redis_metrics_channel: str = "risk.metrics.live"

    postgres_dsn: str = Field(
        default="postgresql+asyncpg://risk:risk@postgres:5432/risk_monitor",
        validation_alias=AliasChoices("DATABASE_URL", "POSTGRES_DSN", "postgres_dsn"),
    )

    jwt_secret_key: str = Field(
        default="change-me-in-prod",
        validation_alias=AliasChoices("JWT_SECRET", "jwt_secret_key"),
    )
    jwt_algorithm: str = "HS256"
    jwt_access_token_minutes: int = 60
    jwt_refresh_secret_key: str = Field(
        default="change-me-refresh-secret",
        validation_alias=AliasChoices("JWT_REFRESH_SECRET", "jwt_refresh_secret_key"),
    )
    jwt_refresh_token_minutes: int = 10080


    frontend_base_url: str = Field(
        default="http://app.localhost",
        validation_alias=AliasChoices("FRONTEND_BASE_URL", "frontend_base_url"),
    )

    google_oauth_client_id: str = Field(
        default="",
        validation_alias=AliasChoices("GOOGLE_OAUTH_CLIENT_ID", "google_oauth_client_id"),
    )
    google_oauth_client_secret: str = Field(
        default="",
        validation_alias=AliasChoices("GOOGLE_OAUTH_CLIENT_SECRET", "google_oauth_client_secret"),
    )
    google_oauth_redirect_uri: str = Field(
        default="http://api.localhost/v1/auth/google/callback",
        validation_alias=AliasChoices("GOOGLE_OAUTH_REDIRECT_URI", "google_oauth_redirect_uri"),
    )

    apple_oauth_client_id: str = Field(
        default="",
        validation_alias=AliasChoices("APPLE_OAUTH_CLIENT_ID", "apple_oauth_client_id"),
    )
    apple_oauth_client_secret: str = Field(
        default="",
        validation_alias=AliasChoices("APPLE_OAUTH_CLIENT_SECRET", "apple_oauth_client_secret"),
    )
    apple_oauth_redirect_uri: str = Field(
        default="http://api.localhost/v1/auth/apple/callback",
        validation_alias=AliasChoices("APPLE_OAUTH_REDIRECT_URI", "apple_oauth_redirect_uri"),
    )
    ml_inference_url: str = "http://ml-inference:8000"
    feature_enrichment_url: str = "http://feature-enrichment:8000"
    data_connector_url: str = "http://data-connector:8030"
    max_event_retries: int = 3
    dedupe_ttl_seconds: int = 3600
    connector_poll_seconds: int = 60
    connectors_v2_enabled: bool = True
    connector_http_timeout_seconds: int = 30
    connector_max_retries: int = 3
    connector_backoff_max_seconds: int = 1800
    connector_circuit_breaker_failures: int = 5
    connector_jitter_seconds: int = 15

    # Data connector source configuration.
    ofac_sls_url: str = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.CSV"
    opensanctions_url: str = "https://api.opensanctions.org/match/default"
    opensanctions_api_key: str = ""
    fatf_source_url: str = "https://www.fatf-gafi.org/en/topics/high-risk-and-other-monitored-jurisdictions.html"
    ipinfo_base_url: str = "https://ipinfo.io"
    ipinfo_token: str = ""
    binlist_base_url: str = "https://lookup.binlist.net"
    maxmind_download_url: str = ""
    maxmind_license_key: str = ""
    maxmind_account_id: str = ""
    ecb_fx_url: str = "https://data-api.ecb.europa.eu/service/data"
    hibp_base_url: str = "https://haveibeenpwned.com/api/v3"
    hibp_api_key: str = ""
    connector_enable_ofac: bool = True
    connector_enable_fatf: bool = True
    connector_enable_ecb: bool = True
    connector_enable_maxmind: bool = True
    connector_enable_opensanctions: bool = False
    connector_enable_ipinfo: bool = False
    connector_enable_binlist: bool = False
    connector_enable_hibp: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    def uvicorn_config(self) -> dict:
        """Return host/port settings for Uvicorn startup."""
        return {"host": self.api_host, "port": self.api_port}


class ApiGatewaySettings(BaseServiceSettings):
    service_name: str = "api-gateway"
    cors_allow_origins: str = "http://app.localhost,http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origins(self) -> list[str]:
        """Split configured CORS origins into a validated list."""
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]


class WorkerSettings(BaseServiceSettings):
    service_name: str = "event-worker"
    api_port: int = 8010


class MLSettings(BaseServiceSettings):
    service_name: str = "ml-inference"
    api_port: int = 8000
    model_dir: str = Field(
        default="/models",
        validation_alias=AliasChoices("MODEL_DIR", "model_dir"),
    )
    default_model_name: str = "risk_autoencoder"


class NotificationSettings(BaseServiceSettings):
    service_name: str = "notification-service"
    api_port: int = 8020


class DataConnectorSettings(BaseServiceSettings):
    service_name: str = "data-connector-service"
    api_port: int = 8030


class FeatureEnrichmentSettings(BaseServiceSettings):
    service_name: str = "feature-enrichment-service"
    api_port: int = 8040


class MetricsAggregatorSettings(BaseServiceSettings):
    service_name: str = "metrics-aggregator-service"
    api_port: int = 8050
