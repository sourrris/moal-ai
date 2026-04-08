import sys

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseServiceSettings(BaseSettings):
    service_name: str = "unknown-service"
    environment: str = "development"
    log_level: str = "INFO"

    # nosec B104
    # Intentional: this service binds all interfaces inside a container.
    api_host: str = "0.0.0.0"
    api_port: int = 8000

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

    ml_inference_url: str = "http://ml-inference:8000"

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
                f"[MOAL WARNING] JWT secrets are using placeholder values in environment '{env_name}'. "
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

        if errors:
            raise ValueError(f"Secret validation failed for environment '{env_name}': " + "; ".join(errors))
        return self

    def uvicorn_config(self) -> dict:
        """Return host/port settings for Uvicorn startup."""
        return {"host": self.api_host, "port": self.api_port}


class ApiGatewaySettings(BaseServiceSettings):
    service_name: str = "api-gateway"
    cors_allow_origins: str = "http://app.localhost,http://localhost:5173,http://127.0.0.1:5173"
    cors_allow_origin_regex: str = ""

    @property
    def cors_origins(self) -> list[str]:
        """Split configured CORS origins into a validated list."""
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]

    @property
    def cors_origin_regex(self) -> str | None:
        """Optional regex for matching dynamic origins (e.g. Vercel preview deploys)."""
        return self.cors_allow_origin_regex or None


class MLSettings(BaseServiceSettings):
    service_name: str = "ml-inference"
    api_port: int = 8000
    model_dir: str = Field(
        default="/models",
        validation_alias=AliasChoices("MODEL_DIR", "model_dir"),
    )
    default_model_name: str = "risk_autoencoder"
