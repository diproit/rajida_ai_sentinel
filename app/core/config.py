from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Application settings
    APP_NAME: str = "DigiValuer Sentinel"
    APP_ENV: str = "development"
    DEBUG: bool = True
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8001
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = "dev_secret_key_change_in_production_1234567890"

    # Database
    POSTGRES_USER: str = "sentinel"
    POSTGRES_PASSWORD: str = "sentinel_secret"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "digivaluer_sentinel"
    DATABASE_URL: str = "postgresql+asyncpg://sentinel:sentinel_secret@localhost:5432/digivaluer_sentinel"
    DB_ECHO: bool = False

    # Redis & Celery
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    # Google Gemini LLM API (LangChain / Google GenAI)
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.0-flash"
    GEMINI_TEMPERATURE: float = 0.2

    # DigiValuer Platform Integration
    DIGIVALUER_API_BASE_URL: str = "https://api.digivaluer.example.com/v1"
    DIGIVALUER_API_KEY: Optional[str] = None
    DIGIVALUER_API_TIMEOUT_SECONDS: int = 30
    DIGIVALUER_WEBHOOK_SECRET: Optional[str] = None

    # Agentic Workflow, Human-in-the-Loop & Polling
    HUMAN_IN_THE_LOOP: bool = True
    SCAN_INTERVAL_MINUTES: int = 30
    POLLING_INTERVAL_SECONDS: int = 60
    VALUATION_STALL_THRESHOLD_HOURS: int = 24
    AUTO_ESCALATION_ENABLED: bool = True
    AGENT_MAX_ITERATIONS: int = 10

    # Notification Services (SendGrid, Twilio, Webhooks)
    SENDGRID_API_KEY: Optional[str] = None
    EMAIL_FROM_ADDRESS: str = "sentinel@digivaluer.example.com"
    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    TWILIO_PHONE_NUMBER: Optional[str] = None


@lru_cache()
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
