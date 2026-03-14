import sys
import warnings

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseServiceSettings(BaseSettings):
    service_name: str = "unknown-service"
    environment: str = "development"
    log_level: str = "INFO"

    api_host: str = "0.0.0.0"  # nosec B104 — intentional: microservice binds all interfaces in container
    api_port: int = 8000

    rabbitmq_url: str = Field(
        default="amqp://guest:guest@rabbitmq:5672/",
        validation_alias=AliasChoices("RABBITMQ_URL", "rabbitmq_url"),
    )
    # Primary standardized RabbitMQ identifiers.
    rabbitmq_events_exchange: str = "risk.event.exchange"
    rabbitmq_events_routing_key: str = "risk.event.ingested"
    rabbitmq_events_queue: str = "risk.event.queue"
    rabbitmq_events_v2_routing_key: str = "risk.event.v2.ingested"
    rabbitmq_events_v2_queue: str = "risk.event.v2.queue"
    rabbitmq_events_dlq: str = "risk.event.dlq"
    rabbitmq_alerts_exchange: str = "risk.alert.exchange"
    rabbitmq_alerts_routing_key: str = "risk.alert.raised"
    rabbitmq_alerts_queue: str = "risk.alert.queue"
    rabbitmq_alerts_routing_queue: str = "risk.alert.routing.queue"
    rabbitmq_dlx_exchange: str = "risk.dead-letter.exchange"
    rabbitmq_metrics_exchange: str = "risk.metric.exchange"
    rabbitmq_metrics_routing_key: str = "risk.metric.updated"
    rabbitmq_metrics_queue: str = "risk.metric.queue"
    rabbitmq_reference_exchange: str = "risk.reference-data.exchange"
    rabbitmq_reference_routing_key: str = "risk.reference-data.updated"
    rabbitmq_reference_queue: str = "risk.reference-data.queue"
    # Legacy RabbitMQ identifiers retained for staged cutover compatibility.
    rabbitmq_events_exchange_legacy: str = "risk.events.exchange"
    rabbitmq_events_routing_key_legacy: str = "risk.events.ingested"
    rabbitmq_events_queue_legacy: str = "risk.events.queue"
    rabbitmq_events_v2_routing_key_legacy: str = "risk.events.v2.ingested"
    rabbitmq_events_v2_queue_legacy: str = "risk.events.v2.queue"
    rabbitmq_events_dlq_legacy: str = "risk.events.dlq"
    rabbitmq_alerts_exchange_legacy: str = "risk.alerts.exchange"
    rabbitmq_alerts_routing_key_legacy: str = "risk.alerts.raised"
    rabbitmq_alerts_queue_legacy: str = "risk.alerts.queue"
    rabbitmq_alerts_routing_queue_legacy: str = "risk.alerts.routing.queue"
    rabbitmq_dlx_exchange_legacy: str = "risk.deadletter.exchange"
    rabbitmq_metrics_exchange_legacy: str = "risk.metrics.exchange"
    rabbitmq_metrics_routing_key_legacy: str = "risk.metrics.updated"
    rabbitmq_metrics_queue_legacy: str = "risk.metrics.queue"
    rabbitmq_reference_exchange_legacy: str = "risk.reference.exchange"
    rabbitmq_reference_routing_key_legacy: str = "risk.reference.updated"
    rabbitmq_reference_queue_legacy: str = "risk.reference.queue"
    rabbitmq_queue_type: str = "classic"
    rabbitmq_heartbeat_seconds: int = 60
    rabbitmq_connection_timeout_seconds: int = 10

    redis_url: str = Field(
        default="redis://redis:6379/0",
        validation_alias=AliasChoices("REDIS_URL", "redis_url"),
    )
    # Primary standardized Redis channels.
    redis_alert_channel: str = "risk.live.alerts"
    redis_metrics_channel: str = "risk.live.metrics"
    # Legacy channels retained for staged cutover compatibility.
    redis_alert_channel_legacy: str = "risk.alerts.live"
    redis_metrics_channel_legacy: str = "risk.metrics.live"

    postgres_dsn: str = Field(
        default="postgresql+asyncpg://risk:risk@postgres:5432/risk_monitor",
        validation_alias=AliasChoices("DATABASE_URL", "POSTGRES_DSN", "postgres_dsn"),
    )

    jwt_secret_key: str = Field(
        default="change-me-in-prod",
        validation_alias=AliasChoices("JWT_SECRET", "jwt_secret_key"),
    )
    jwt_algorithm: str = "HS256"
    jwt_private_key_pem: str = Field(
        default="",
        validation_alias=AliasChoices("JWT_PRIVATE_KEY_PEM", "jwt_private_key_pem"),
    )
    jwt_public_key_pem: str = Field(
        default="",
        validation_alias=AliasChoices("JWT_PUBLIC_KEY_PEM", "jwt_public_key_pem"),
    )
    jwt_key_id: str = Field(
        default="aegis-default-kid",
        validation_alias=AliasChoices("JWT_KEY_ID", "jwt_key_id"),
    )
    jwt_access_token_minutes: int = 60
    jwt_refresh_secret_key: str = Field(
        default="change-me-refresh-secret",
        validation_alias=AliasChoices("JWT_REFRESH_SECRET", "jwt_refresh_secret_key"),
    )
    jwt_refresh_token_minutes: int = 10080
    auth_access_cookie_name: str = Field(
        default="aegis_access_token",
        validation_alias=AliasChoices("AUTH_ACCESS_COOKIE_NAME", "auth_access_cookie_name"),
    )
    auth_refresh_cookie_name: str = Field(
        default="aegis_refresh_token",
        validation_alias=AliasChoices("AUTH_REFRESH_COOKIE_NAME", "auth_refresh_cookie_name"),
    )
    auth_cookie_domain: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AUTH_COOKIE_DOMAIN", "auth_cookie_domain"),
    )
    auth_cookie_secure: bool = Field(
        default=False,
        validation_alias=AliasChoices("AUTH_COOKIE_SECURE", "auth_cookie_secure"),
    )
    auth_cookie_samesite: str = Field(
        default="lax",
        validation_alias=AliasChoices("AUTH_COOKIE_SAMESITE", "auth_cookie_samesite"),
    )


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
    api_gateway_url: str = Field(
        default="http://api-gateway:8000",
        validation_alias=AliasChoices("API_GATEWAY_URL", "api_gateway_url"),
    )
    max_event_retries: int = 3
    dedupe_ttl_seconds: int = 3600
    connector_poll_seconds: int = 60
    connectors_v2_enabled: bool = True
    connector_http_timeout_seconds: int = 30
    connector_max_retries: int = 3
    connector_backoff_max_seconds: int = 1800
    connector_circuit_breaker_failures: int = 5
    connector_jitter_seconds: int = 15
    connector_reference_modules: str = "aegis_connectors.reference_plugins"
    connector_ingest_modules: str = "aegis_connectors.ingest_plugins"
    connector_source_route_map_json: str = "{}"
    connector_auto_ingest_on_reference_update: bool = True
    connector_auto_ingest_tenant_id: str = "tenant-alpha"
    connector_auto_ingest_subject: str = "connector-service"
    connector_auto_ingest_timeout_seconds: int = 10
    tenant_config_enforcement_mode: str = "permissive"
    control_api_url: str = "http://control-api:8060"
    alert_router_timeout_seconds: int = 10
    alert_router_max_attempts: int = 3
    alert_router_webhook_signing_secret: str = "change-me-alert-router-signing"
    alert_router_email_smtp_host: str = "localhost"
    alert_router_email_smtp_port: int = 587
    alert_router_email_smtp_username: str = Field(
        default="",
        validation_alias=AliasChoices("SMTP_USERNAME", "alert_router_email_smtp_username"),
    )
    alert_router_email_smtp_password: str = Field(
        default="",
        validation_alias=AliasChoices("SMTP_PASSWORD", "alert_router_email_smtp_password"),
    )
    alert_router_email_smtp_tls: bool = Field(
        default=True,
        validation_alias=AliasChoices("SMTP_TLS", "alert_router_email_smtp_tls"),
    )
    alert_router_email_from: str = "no-reply@aegis.local"
    model_activation_min_samples: int = Field(
        default=64,
        validation_alias=AliasChoices("MODEL_ACTIVATION_MIN_SAMPLES", "model_activation_min_samples"),
    )
    model_activation_min_relative_improvement: float = Field(
        default=0.02,
        validation_alias=AliasChoices(
            "MODEL_ACTIVATION_MIN_RELATIVE_IMPROVEMENT",
            "model_activation_min_relative_improvement",
        ),
    )
    model_activation_threshold_ratio_min: float = Field(
        default=0.5,
        validation_alias=AliasChoices("MODEL_ACTIVATION_THRESHOLD_RATIO_MIN", "model_activation_threshold_ratio_min"),
    )
    model_activation_threshold_ratio_max: float = Field(
        default=2.0,
        validation_alias=AliasChoices("MODEL_ACTIVATION_THRESHOLD_RATIO_MAX", "model_activation_threshold_ratio_max"),
    )

    # Data connector source configuration.
    ofac_sls_url: str = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.CSV"
    fatf_source_url: str = "https://www.fatf-gafi.org/en/countries/black-and-grey-lists.html"
    ecb_fx_url: str = "https://data-api.ecb.europa.eu/service/data"
    mempool_api_url: str = "https://mempool.space/api"
    abusech_api_url: str = "https://abuse.ch/api/v1"
    abusech_ip_blocklist_url: str = "https://feodotracker.abuse.ch/downloads/ipblocklist_recommended.txt"
    connector_enable_ofac: bool = True
    connector_enable_fatf: bool = True
    connector_enable_ecb: bool = True
    connector_enable_mempool: bool = True
    connector_enable_abusech: bool = True

    sentry_dsn: str = Field(
        default="",
        validation_alias=AliasChoices("SENTRY_DSN", "sentry_dsn"),
    )
    sentry_traces_sample_rate: float = Field(
        default=0.1,
        validation_alias=AliasChoices("SENTRY_TRACES_SAMPLE_RATE", "sentry_traces_sample_rate"),
    )

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @staticmethod
    def _is_placeholder_secret(value: str) -> bool:
        normalized = (value or "").strip()
        if not normalized:
            return True
        return normalized in {
            "change-me-in-prod",
            "change-me-refresh-secret",
            "change-me-alert-router-signing",
            "changeme",
            "default",
            "secret",
        }

    @model_validator(mode="after")
    def _validate_production_secrets(self) -> "BaseServiceSettings":
        env_name = (self.environment or "").strip().lower()
        is_strict = env_name in {"prod", "production", "staging", "stage"}

        using_placeholder = (
            self.jwt_algorithm.upper().startswith("HS")
            and (
                self._is_placeholder_secret(self.jwt_secret_key)
                or len(self.jwt_secret_key) < 32
                or self._is_placeholder_secret(self.jwt_refresh_secret_key)
                or len(self.jwt_refresh_secret_key) < 32
            )
        )

        if using_placeholder and not is_strict:
            print(
                f"[AEGIS WARNING] JWT secrets are using placeholder values in environment '{env_name}'. "
                "Set JWT_SECRET and JWT_REFRESH_SECRET before deploying.",
                file=sys.stderr,
            )

        if not is_strict:
            return self

        errors: list[str] = []
        if self.jwt_algorithm.upper().startswith("HS"):
            if self._is_placeholder_secret(self.jwt_secret_key) or len(self.jwt_secret_key) < 32:
                errors.append("JWT_SECRET must be set to a non-default value with length >= 32 for HS* algorithms")
            if self._is_placeholder_secret(self.jwt_refresh_secret_key) or len(self.jwt_refresh_secret_key) < 32:
                errors.append("JWT_REFRESH_SECRET must be set to a non-default value with length >= 32")
        elif self.jwt_algorithm.upper().startswith("RS"):
            if "BEGIN" not in self.jwt_private_key_pem:
                errors.append("JWT_PRIVATE_KEY_PEM must be set for RS* algorithms")
            if "BEGIN" not in self.jwt_public_key_pem:
                errors.append("JWT_PUBLIC_KEY_PEM must be set for RS* algorithms")

        if self._is_placeholder_secret(self.alert_router_webhook_signing_secret):
            errors.append("ALERT_ROUTER_WEBHOOK_SIGNING_SECRET must be set to a non-default value")

        samesite = (self.auth_cookie_samesite or "").strip().lower()
        if samesite not in {"lax", "strict", "none"}:
            errors.append("AUTH_COOKIE_SAMESITE must be one of: lax, strict, none")

        if errors:
            raise ValueError(f"Secret validation failed for environment '{env_name}': " + "; ".join(errors))
        return self

    @property
    def jwt_uses_asymmetric(self) -> bool:
        return self.jwt_algorithm.upper().startswith(("RS", "PS", "ES"))

    @property
    def jwt_signing_key(self) -> str:
        if self.jwt_uses_asymmetric:
            return self.jwt_private_key_pem
        return self.jwt_secret_key

    @property
    def jwt_verification_key(self) -> str:
        if self.jwt_uses_asymmetric:
            return self.jwt_public_key_pem
        return self.jwt_secret_key

    @property
    def jwt_refresh_signing_key(self) -> str:
        if self.jwt_uses_asymmetric:
            return self.jwt_private_key_pem
        return self.jwt_refresh_secret_key

    @property
    def jwt_refresh_verification_key(self) -> str:
        if self.jwt_uses_asymmetric:
            return self.jwt_public_key_pem
        return self.jwt_refresh_secret_key

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


class ControlPlaneSettings(BaseServiceSettings):
    service_name: str = "control-api"
    api_port: int = 8060
    cors_allow_origins: str = "http://control.localhost,http://ops-control.localhost,http://localhost:5174,http://localhost:5175"


class AlertRouterSettings(BaseServiceSettings):
    service_name: str = "alert-router"
    api_port: int = 8061
