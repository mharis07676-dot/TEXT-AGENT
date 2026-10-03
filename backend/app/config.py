from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def to_async_postgres_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


def to_sync_postgres_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Synas Labs Text Agent"
    app_env: str = "development"
    debug: bool = True
    secret_key: str = "change-me-in-production"
    api_prefix: str = "/api/v1"

    database_url: str = "postgresql+asyncpg://synas:synas@localhost:5432/synas_text_agent"
    database_url_sync: str = "postgresql://synas:synas@localhost:5432/synas_text_agent"

    jwt_secret: str = "change-me-jwt-secret"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    openai_api_key: str = ""
    openai_text_model: str = "gpt-4.1-mini"

    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_api_key_sid: str = ""
    twilio_api_key_secret: str = ""
    twilio_sms_from_number: str = ""
    twilio_whatsapp_from: str = ""
    twilio_webhook_base_url: str = ""

    default_tenant_slug: str = "synas"
    bootstrap_admin_email: str = "admin@synas.local"
    bootstrap_admin_password: str = "changeme123"
    bootstrap_admin_name: str = "Synas Admin"
    cors_origins: str = "http://localhost:3000"
    max_inbound_message_chars: int = 4000

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_async_database_url(cls, value: str) -> str:
        return to_async_postgres_url(value)

    @field_validator("database_url_sync", mode="before")
    @classmethod
    def normalize_sync_database_url(cls, value: str) -> str:
        return to_sync_postgres_url(value)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod", "staging"}

    @property
    def twilio_configured(self) -> bool:
        return bool(self.twilio_account_sid and self.twilio_auth_token)

    @property
    def sms_configured(self) -> bool:
        return self.twilio_configured and bool(self.twilio_sms_from_number)

    @property
    def whatsapp_configured(self) -> bool:
        return self.twilio_configured and bool(self.twilio_whatsapp_from)

    @property
    def openai_configured(self) -> bool:
        return bool(self.openai_api_key)


def _is_placeholder(value: str) -> bool:
    normalized = (value or "").strip().lower()
    return normalized in {"", "change-me-in-production", "change-me-jwt-secret"}


def validate_required_settings(settings: Settings) -> None:
    """Fail fast on missing production bootstrap vars. Never log secret values.

    Twilio / OpenAI are optional at boot so Railway can deploy a healthy API
    before messaging credentials are configured. Feature health is exposed via
    /health and /api/v1/messaging/health instead.
    """
    missing: list[str] = []

    if settings.is_production:
        checks = [
            ("DATABASE_URL", settings.database_url),
            ("JWT_SECRET", settings.jwt_secret),
            ("SECRET_KEY", settings.secret_key),
        ]
        for name, value in checks:
            if _is_placeholder(value):
                missing.append(name)

    ordered_missing = list(dict.fromkeys(missing))
    if ordered_missing:
        names = ", ".join(ordered_missing)
        raise RuntimeError(f"Missing required environment variable: {names}")


@lru_cache
def get_settings() -> Settings:
    return Settings()
