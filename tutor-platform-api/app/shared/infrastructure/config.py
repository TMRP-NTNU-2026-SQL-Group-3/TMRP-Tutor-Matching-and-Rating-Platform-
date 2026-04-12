from pydantic import Field, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database (PostgreSQL) — URL is required; env-only so it is never committed.
    database_url: str = Field(...)
    db_pool_min: int = 2
    db_pool_max: int = 10

    # JWT — secret is required; Settings() construction fails without it in env/.env
    jwt_secret_key: str = Field(..., min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 15  # short-lived access token (paired with refresh token)

    # Super-admin seeded on startup — password required via env.
    admin_username: str = "admin"
    admin_password: str = Field(..., min_length=8)

    # Reviews become immutable after this many days.
    review_lock_days: int = 7

    # Admin CSV/ZIP import caps (infra knob, not a domain rule)
    admin_max_upload_bytes: int = 50 * 1024 * 1024
    admin_max_import_rows_per_table: int = 50_000

    # huey task queue
    huey_db_path: str = "data/huey.db"

    # Logging
    log_file: str = "logs/app.log"
    log_level: str = "INFO"
    log_format: str = "json"

    # CORS
    cors_origins: str = "http://localhost:5173"

    class Config:
        env_file = ".env"

    @model_validator(mode="after")
    def reject_placeholder_secrets(self):
        # Defence-in-depth against someone re-introducing the old placeholders via env.
        if self.jwt_secret_key in {"change-me-in-production", "change-me"}:
            raise ValueError(
                "JWT_SECRET_KEY must be a real secret. "
                "Generate with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        if self.admin_password in {"admin123", "admin", "password"}:
            raise ValueError("ADMIN_PASSWORD must not be a known placeholder value.")
        return self


settings = Settings()
