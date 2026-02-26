from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseServiceSettings(BaseSettings):
    service_name: str = "unknown-service"
    environment: str = "development"
    log_level: str = "INFO"

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"
    rabbitmq_events_exchange: str = "risk.events.exchange"
    rabbitmq_events_routing_key: str = "risk.events.ingested"
    rabbitmq_events_queue: str = "risk.events.queue"
    rabbitmq_events_dlq: str = "risk.events.dlq"
    rabbitmq_alerts_exchange: str = "risk.alerts.exchange"
    rabbitmq_alerts_routing_key: str = "risk.alerts.raised"
    rabbitmq_alerts_queue: str = "risk.alerts.queue"
    rabbitmq_dlx_exchange: str = "risk.deadletter.exchange"

    redis_url: str = "redis://redis:6379/0"
    redis_alert_channel: str = "risk.alerts.live"

    postgres_dsn: str = "postgresql+asyncpg://risk:risk@postgres:5432/risk_monitor"

    jwt_secret_key: str = "change-me-in-prod"
    jwt_algorithm: str = "HS256"
    jwt_access_token_minutes: int = 60

    ml_inference_url: str = "http://ml-inference:8000"
    max_event_retries: int = 3
    dedupe_ttl_seconds: int = 3600

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    def uvicorn_config(self) -> dict:
        return {"host": self.api_host, "port": self.api_port}


class ApiGatewaySettings(BaseServiceSettings):
    service_name: str = "api-gateway"
    cors_allow_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]


class WorkerSettings(BaseServiceSettings):
    service_name: str = "event-worker"
    api_port: int = 8010


class MLSettings(BaseServiceSettings):
    service_name: str = "ml-inference"
    api_port: int = 8000
    model_dir: str = "/models"
    default_model_name: str = "risk_autoencoder"


class NotificationSettings(BaseServiceSettings):
    service_name: str = "notification-service"
    api_port: int = 8020
