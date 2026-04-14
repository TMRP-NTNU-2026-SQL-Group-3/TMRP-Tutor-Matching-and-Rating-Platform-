from pydantic import Field, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database (PostgreSQL) — URL is required; env-only so it is never committed.
    database_url: str = Field(...)
    db_pool_min: int = 2
    db_pool_max: int = 10

    # JWT — secret is required; Settings() construction fails without it in env/.env
    jwt_secret_key: str = Field(..., min_length=32)
    # 上一版密鑰：輪換期間仍接受其簽發的 token，避免 in-flight session 立刻 401。
    # 留空表示沒有過渡期。長度限制亦為 32 字元（沿用同強度），允許留白以表示停用。
    jwt_secret_key_previous: str = ""
    jwt_algorithm: str = "HS256"
    # M-01: default lowered from 15 to 5 minutes. Access tokens live in
    # localStorage (pending migration to HttpOnly cookies), so the access-
    # token TTL is the main bound on an XSS-stolen credential. Shorter TTL
    # means a refresh flow round-trip more often — acceptable at this scale.
    jwt_expire_minutes: int = 5

    # Super-admin seeded on startup — password required via env.
    admin_username: str = "admin"
    admin_password: str = Field(..., min_length=8)

    # Reviews become immutable after this many days.
    review_lock_days: int = 7

    # Admin CSV/ZIP import caps (infra knob, not a domain rule)
    admin_max_upload_bytes: int = 50 * 1024 * 1024
    admin_max_import_rows_per_table: int = 50_000

    # Phase 4 A2: global HTTP request body cap enforced by
    # BodySizeLimitMiddleware. Defaults to the admin upload cap so the
    # largest legitimate payload (CSV/ZIP import) still fits.
    max_request_body_bytes: int = 50 * 1024 * 1024

    # huey task queue
    huey_db_path: str = "data/huey.db"

    # Logging
    log_file: str = "logs/app.log"
    log_level: str = "INFO"
    log_format: str = "json"

    # CORS
    cors_origins: str = "http://localhost:5173"

    # Operational toggle. When False, FastAPI suppresses /docs, /redoc and the
    # OpenAPI JSON so production deployments don't leak the full route list.
    debug: bool = False

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
        # Same enforcement applies to the rotation slot when set — otherwise an
        # operator could "rotate" to a placeholder and reopen the verification path.
        if self.jwt_secret_key_previous and len(self.jwt_secret_key_previous) < 32:
            raise ValueError("JWT_SECRET_KEY_PREVIOUS, when set, must also be >= 32 chars.")
        if self.jwt_secret_key_previous == self.jwt_secret_key:
            raise ValueError("JWT_SECRET_KEY_PREVIOUS must differ from JWT_SECRET_KEY.")
        if self.admin_password in {"admin123", "admin", "password"}:
            raise ValueError("ADMIN_PASSWORD must not be a known placeholder value.")
        return self


settings = Settings()
