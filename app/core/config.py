import json
from typing import Any, List

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources import EnvSettingsSource

# Monkey-patch EnvSettingsSource to fall back to comma-splitting for known list fields.
# This affects both EnvSettingsSource and DotEnvSettingsSource (its subclass).
_original_decode_complex_value = EnvSettingsSource.decode_complex_value


def _decode_complex_value(self, field_name: str, field, value: str) -> Any:
    try:
        return _original_decode_complex_value(self, field_name, field, value)
    except json.JSONDecodeError:
        if field_name in {"ALLOWED_ORIGINS", "CORS_ALLOW_METHODS", "CORS_ALLOW_HEADERS"}:
            return [item.strip() for item in value.split(",") if item.strip()]
        raise


EnvSettingsSource.decode_complex_value = _decode_complex_value


class Settings(BaseSettings):
    PROJECT_NAME: str = "amazon-ebay-reseller"
    VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"

    # Database — no default to prevent accidental deployments with hardcoded credentials
    DATABASE_URL: str
    DATABASE_URL_SYNC: str

    # Redis connection components (used to build URLs below)
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = ""

    # Derived Redis URLs — can be overridden by env var, otherwise built from components
    REDIS_URL: str = ""
    CELERY_BROKER_URL: str = ""
    CELERY_RESULT_BACKEND: str = ""

    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]

    # Security — no default to prevent accidental deployments with a hardcoded secret
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    ALGORITHM: str = "HS256"

    CORS_ALLOW_METHODS: List[str] = ["GET", "POST", "PATCH", "DELETE", "OPTIONS"]
    CORS_ALLOW_HEADERS: List[str] = ["Authorization", "Content-Type", "X-Request-ID"]
    CORS_ALLOW_CREDENTIALS: bool = True

    RATE_LIMIT_DEFAULT: str = "100/minute"
    RATE_LIMIT_AUTH: str = "10/minute"

    # Amazon Product Advertising API
    AMAZON_ACCESS_KEY: str = ""
    AMAZON_SECRET_KEY: str = ""
    AMAZON_PARTNER_TAG: str = ""
    AMAZON_HOST: str = "webservices.amazon.com"
    AMAZON_REGION: str = "us-east-1"

    # eBay API
    EBAY_CLIENT_ID: str = ""
    EBAY_CLIENT_SECRET: str = ""
    EBAY_DEV_ID: str = ""
    EBAY_RU_NAME: str = ""
    EBAY_SITE_ID: int = 0
    EBAY_API_BASE_URL: str = "https://api.ebay.com"

    # Celery schedules
    STOCK_SYNC_INTERVAL: int = 21600  # 6 hours
    PRICE_SYNC_INTERVAL: int = 7200   # 2 hours

    # Sourcing defaults
    DEFAULT_PROFIT_MARGIN_THRESHOLD: float = 0.15
    DEFAULT_MAX_PRICE_USD: float = 200.0
    DEFAULT_MIN_PRICE_USD: float = 5.0

    # Sync defaults
    DEFAULT_AVAILABLE_QUANTITY: int = 5
    PRICE_SYNC_MIN_DELTA_PERCENT: float = 1.0

    # Resilience / Circuit Breaker
    CB_FAILURE_THRESHOLD: int = 5
    CB_RECOVERY_TIMEOUT_SECONDS: float = 60.0
    CB_HALF_OPEN_MAX_CALLS: int = 3

    # Retry / Backoff
    RETRY_MAX_RETRIES: int = 3
    RETRY_BASE_DELAY_SECONDS: float = 1.0
    RETRY_MAX_DELAY_SECONDS: float = 60.0
    RETRY_EXPONENTIAL_BASE: float = 2.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    @model_validator(mode="after")
    def build_redis_urls(self) -> "Settings":
        auth = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        base = f"redis://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        if not self.REDIS_URL:
            self.REDIS_URL = base
        if not self.CELERY_BROKER_URL:
            self.CELERY_BROKER_URL = base
        if not self.CELERY_RESULT_BACKEND:
            self.CELERY_RESULT_BACKEND = base
        return self


settings = Settings()
