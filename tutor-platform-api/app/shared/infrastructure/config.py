from pydantic import Field, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database (PostgreSQL) — URL is required; env-only so it is never committed.
    database_url: str = Field(...)
    # Pool min should be >= number of uvicorn workers to avoid starvation
    # under burst load. Default 5 covers a typical 2–4 worker deployment.
    db_pool_min: int = 5
    db_pool_max: int = 10

    # JWT — secret is required; Settings() construction fails without it in env/.env
    jwt_secret_key: str = Field(..., min_length=32)
    # 上一版密鑰：輪換期間仍接受其簽發的 token，避免 in-flight session 立刻 401。
    # 留空表示沒有過渡期。長度限制亦為 32 字元（沿用同強度），允許留白以表示停用。
    jwt_secret_key_previous: str = ""
    # HS256 (symmetric) is sufficient for single-service deployments.
    # Federated or multi-service auth requires RS256/ES256 with a keypair;
    # switching also needs changes to decode_access_token's verification logic.
    jwt_algorithm: str = "HS256"
    # SEC-C02: access tokens are now in HttpOnly cookies (M-01 complete).
    # The 5-minute TTL remains appropriate as defence in depth.
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

    # SEC-C02: auth cookies. Secure=True requires HTTPS — set to True in
    # production (.env.docker), leave False for local HTTP development.
    cookie_secure: bool = False

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
        # INFO-2: auth cookies must carry the Secure flag in production so they
        # are never transmitted over plain HTTP. debug=False is our proxy for
        # "non-local deployment"; operators who terminate TLS at a reverse proxy
        # must still set COOKIE_SECURE=true.
        if not self.debug and not self.cookie_secure:
            raise ValueError(
                "COOKIE_SECURE must be true when DEBUG is false "
                "(auth cookies require the Secure flag in production)."
            )
        # INFO-3: the literal 'admin' username is enumeration bait. Require an
        # operator-chosen bootstrap username in production deployments; also
        # reject the onboarding placeholder so it cannot silently ship to prod.
        if not self.debug and self.admin_username.lower() in {"admin", "owner_change_me"}:
            raise ValueError(
                "ADMIN_USERNAME must not be 'admin' or the onboarding placeholder "
                "when DEBUG is false. Choose an enumeration-resistant form, "
                "e.g. owner_<random6>."
            )
        # LOW-1: CORS origins must be an explicit allow-list. With
        # allow_credentials=True a misconfigured "*" or scheme-less entry would
        # silently trust arbitrary origins. Reject wildcards outright; require
        # https:// outside debug mode so prod cannot accept http:// origins.
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        if not origins:
            raise ValueError("CORS_ORIGINS must contain at least one origin.")
        for origin in origins:
            if origin == "*":
                raise ValueError(
                    "CORS_ORIGINS must not contain '*' when credentials are enabled."
                )
            if self.debug:
                if not (origin.startswith("http://") or origin.startswith("https://")):
                    raise ValueError(
                        f"CORS origin {origin!r} must start with http:// or https://."
                    )
            else:
                if not origin.startswith("https://"):
                    raise ValueError(
                        f"CORS origin {origin!r} must use https:// in non-debug mode."
                    )
        return self


settings = Settings()
