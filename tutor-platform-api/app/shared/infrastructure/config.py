import logging
from datetime import datetime, timedelta, timezone

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database (PostgreSQL) — URL is required; env-only so it is never committed.
    database_url: str = Field(...)
    # Pool min should be >= number of uvicorn workers to avoid starvation
    # under burst load. Default 5 covers a typical 2–4 worker deployment.
    db_pool_min: int = 5
    # I-06: headroom for bursts. Rate-limit checks, handler queries and
    # explicit transactions can each lease one connection concurrently from
    # a single request, so the old cap of 10 was at risk of exhaustion
    # under modest load. Raised to 20; couple this with Postgres max_connections
    # >= (workers * db_pool_max + slack for admin/ops).
    db_pool_max: int = 20
    # I-07: cap the fraction of the pool one user can hold open concurrently.
    # Prevents a single caller from monopolising every connection and
    # starving others (pool-level DoS). Expressed as an absolute count so
    # the bound is obvious in logs.
    db_per_user_quota: int = 5

    # JWT — secret is required; Settings() construction fails without it in env/.env
    jwt_secret_key: str = Field(..., min_length=32)
    # Previous key accepted during rotation so in-flight sessions are not
    # force-logged-out. Empty disables the grace path.
    #
    # Recommended rotation schedule (S-05):
    #   1. Generate a new key:
    #        python -c "import secrets; print(secrets.token_hex(32))"
    #   2. In .env.docker, move JWT_SECRET_KEY to JWT_SECRET_KEY_PREVIOUS and
    #      set JWT_SECRET_KEY_PREVIOUS_EXPIRES_AT to NOW + 7 days (ISO 8601 UTC).
    #   3. Set JWT_SECRET_KEY to the new value and redeploy.
    #   4. After the expiry date passes (at most 7 days), clear both
    #      JWT_SECRET_KEY_PREVIOUS and JWT_SECRET_KEY_PREVIOUS_EXPIRES_AT and
    #      redeploy again to stop accepting tokens signed by the old key.
    # Recommended frequency: rotate every 90 days or immediately upon any
    # suspected exposure.
    jwt_secret_key_previous: str = ""
    # Hard deadline (ISO 8601 UTC, e.g. "2026-05-01T00:00:00Z") after which the
    # previous key is no longer accepted. Required when jwt_secret_key_previous
    # is set so an unbounded grace window cannot linger after rotation — a key
    # kept live "just in case" widens the blast radius of a past leak. A
    # refresh_token's 7-day TTL is the natural upper bound; anything longer is
    # almost certainly an oversight.
    jwt_secret_key_previous_expires_at: str = ""
    # HS256 (symmetric) is sufficient for single-service deployments.
    # Federated or multi-service auth requires RS256/ES256 with a keypair;
    # switching also needs changes to decode_access_token's verification logic.
    jwt_algorithm: str = "HS256"
    # SEC-C02: access tokens are now in HttpOnly cookies (M-01 complete).
    # The 5-minute TTL remains appropriate as defence in depth.
    jwt_expire_minutes: int = 5

    # Super-admin seeded on startup — username and password required via env so
    # deployments cannot silently ship with a guessable literal like 'admin'.
    # Complexity is enforced by reject_weak_admin_password below.
    admin_username: str = Field(..., min_length=3)
    admin_password: str = Field(..., min_length=16)

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

    # SEC-C02: auth cookies. Secure=True requires HTTPS. Defaults to True;
    # set COOKIE_SECURE=false explicitly for local HTTP development.
    cookie_secure: bool = True

    # Operational toggle. When False, FastAPI suppresses /docs, /redoc and the
    # OpenAPI JSON so production deployments don't leak the full route list.
    debug: bool = False

    # SEC-13: controls /docs, /redoc, and /openapi.json independently of DEBUG.
    # Decoupled so that enabling debug mode does not automatically expose the
    # full route inventory. Rejected by the validator when DEBUG is false so it
    # cannot be left on in a production misconfiguration.
    enable_docs: bool = False

    class Config:
        env_file = ".env"

    @model_validator(mode="after")
    def reject_placeholder_secrets(self):
        # ARCH-16: if the per-user quota equals or exceeds the pool max, a
        # single user can exhaust all DB connections before the middleware cap
        # fires, starving every other request.
        if self.db_per_user_quota >= self.db_pool_max:
            raise ValueError(
                f"DB_PER_USER_QUOTA ({self.db_per_user_quota}) must be less than "
                f"DB_POOL_MAX ({self.db_pool_max}) to prevent a single user from "
                "exhausting the connection pool."
            )
        if self.review_lock_days <= 0:
            raise ValueError("REVIEW_LOCK_DAYS must be a positive integer.")
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
        if self.jwt_secret_key_previous and not self.jwt_secret_key_previous_expires_at:
            raise ValueError(
                "JWT_SECRET_KEY_PREVIOUS_EXPIRES_AT is required when "
                "JWT_SECRET_KEY_PREVIOUS is set (ISO 8601 UTC, e.g. "
                "'2026-05-01T00:00:00Z'). An unbounded grace period keeps "
                "a retired key verifiable indefinitely."
            )
        if self.jwt_secret_key_previous_expires_at:
            raw = self.jwt_secret_key_previous_expires_at.strip()
            try:
                deadline = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError(
                    f"JWT_SECRET_KEY_PREVIOUS_EXPIRES_AT must be ISO 8601 UTC: {exc}"
                ) from exc
            if deadline.tzinfo is None:
                raise ValueError(
                    "JWT_SECRET_KEY_PREVIOUS_EXPIRES_AT must include a timezone "
                    "(append 'Z' for UTC)."
                )
            max_deadline = datetime.now(timezone.utc) + timedelta(days=7)
            if deadline > max_deadline:
                raise ValueError(
                    "JWT_SECRET_KEY_PREVIOUS_EXPIRES_AT must not exceed 7 days "
                    "from now (the refresh-token TTL). Rotate the key sooner."
                )
        if self.admin_password in {"admin123", "admin", "password"}:
            raise ValueError("ADMIN_PASSWORD must not be a known placeholder value.")
        # S-H1: 16-char minimum and all four character classes required.
        # 3-of-4 at 12 chars is reachable by offline dictionary attack.
        pw = self.admin_password
        classes = sum([
            any(c.islower() for c in pw),
            any(c.isupper() for c in pw),
            any(c.isdigit() for c in pw),
            any(not c.isalnum() for c in pw),
        ])
        if classes < 4:
            raise ValueError(
                "ADMIN_PASSWORD must contain all four character classes: "
                "lowercase, uppercase, digit, and symbol."
            )
        # INFO-2: auth cookies must carry the Secure flag in production so they
        # are never transmitted over plain HTTP. debug=False is our proxy for
        # "non-local deployment"; operators who terminate TLS at a reverse proxy
        # must still set COOKIE_SECURE=true.
        if not self.debug and not self.cookie_secure:
            raise ValueError(
                "COOKIE_SECURE must be true when DEBUG is false "
                "(auth cookies require the Secure flag in production)."
            )
        # SEC-13: schema endpoints must not be enabled in non-debug (production)
        # deployments — they expose the full route inventory to anonymous callers.
        if self.enable_docs and not self.debug:
            raise ValueError(
                "ENABLE_DOCS must not be true when DEBUG is false. "
                "Schema endpoints expose the full route inventory and "
                "must not be enabled in production deployments."
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
        if self.log_level.upper() == "DEBUG" and not self.debug:
            logging.getLogger(__name__).warning(
                "LOG_LEVEL=DEBUG is active while DEBUG=False; verbose output may "
                "expose sensitive values in log aggregators."
            )
        return self


settings = Settings()
