"""Application settings loaded from environment / .env file.

All secrets and environment-specific values come from here. The committed
`.env.example` documents every key; real `.env` is git-ignored.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Runtime
    APP_ENV: str = "dev"  # dev | prod

    # Security
    SECRET_KEY: str = "dev-only-change-me"
    TOKEN_ALG: str = "HS256"
    FIELD_ENCRYPTION_KEY: str = ""

    # Databases
    DATABASE_URL: str = "sqlite:///./hmsv2.db"
    AUDIT_DATABASE_URL: str = "sqlite:///./hmsv2_audit.db"

    # Clinic
    CLINIC_TZ: str = "Africa/Cairo"
    CURRENCY: str = "EGP"

    # Files
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_MB: int = 15
    CLAMAV_SOCKET: str = ""  # e.g. /var/run/clamav/clamd.ctl (required in prod)

    # CORS
    CORS_STAFF_ORIGINS: list[str] = ["http://localhost:5173"]
    CORS_PUBLIC_ORIGINS: list[str] = ["http://localhost:5174"]

    # Cookies / auth
    ACCESS_COOKIE_NAME: str = "hmsv2_access"
    REFRESH_COOKIE_NAME: str = "hmsv2_refresh"
    CSRF_COOKIE_NAME: str = "hmsv2_csrf"
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "lax"
    ACCESS_TOKEN_MINUTES_STAFF: int = 480
    REFRESH_TOKEN_DAYS_STAFF: int = 30
    ACCESS_TOKEN_MINUTES_PATIENT: int = 240
    REFRESH_TOKEN_DAYS_PATIENT: int = 60

    # Idempotency
    IDEMPOTENCY_TTL_DAYS: int = 7

    # Audit checkpoints
    AUDIT_CHECKPOINT_PRIVATE_KEY_PATH: str = ""
    AUDIT_CHECKPOINT_DIR: str = "./checkpoints"

    # SMTP (empty host = email disabled, rendered to logs)
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASS: str = ""
    SMTP_FROM: str = ""

    # Public API
    RATE_LIMIT_PUBLIC: str = "60/minute"

    @property
    def is_prod(self) -> bool:
        return self.APP_ENV == "prod"

    @property
    def cors_origins(self) -> list[str]:
        return [*self.CORS_STAFF_ORIGINS, *self.CORS_PUBLIC_ORIGINS]


@lru_cache
def get_settings() -> Settings:
    return Settings()
