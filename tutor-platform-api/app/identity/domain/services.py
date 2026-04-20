import logging

from app.shared.infrastructure.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    invalidate_refresh_token,
    verify_password,
)

from .exceptions import (
    DuplicateUsernameError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    InvalidRoleError,
    UserNotFoundError,
)
from .ports import IUserRepository

# L-03: dedicated audit channel so "who logged in from where and when" can be
# reconstructed after the fact. Child of the "app" logger so it inherits the
# rotating JSON file handler set up in setup_logger(). Never log the submitted
# password or issued tokens — the log file is not a credential store.
_audit_logger = logging.getLogger("app.audit")


class AuthService:
    """純業務邏輯：註冊、登入、token 管理。"""

    def __init__(self, user_repo: IUserRepository):
        self._repo = user_repo

    def register(
        self, *, username: str, password: str, display_name: str,
        role: str, phone: str | None, email: str | None,
    ) -> int:
        if role not in ("parent", "tutor"):
            raise InvalidRoleError()

        # M-02: Check duplicates before hashing, but burn an equivalent bcrypt
        # cost on the duplicate path so a timing observer can't distinguish
        # "username taken" from "new user created" and enumerate accounts.
        if self._repo.find_by_username(username):
            hash_password("dummy_for_timing_consistency")
            raise DuplicateUsernameError()

        hashed = hash_password(password)
        return self._repo.register_user(
            username=username,
            password_hash=hashed,
            display_name=display_name,
            role=role,
            phone=phone,
            email=email,
        )

    def login(
        self,
        *,
        username: str,
        password: str,
        source_ip: str | None = None,
        user_agent: str | None = None,
    ) -> dict:
        user = self._repo.find_by_username(username)
        if not user or not verify_password(password, user["password_hash"]):
            # LOW-2: defence in depth — strip CR/LF and truncate before logging
            # in case a caller bypassed the schema validator.
            safe_username = (username or "").replace("\r", "").replace("\n", "")[:64]
            _audit_logger.warning(
                "login_failed username=%s ip=%s ua=%s",
                safe_username, source_ip, user_agent,
            )
            raise InvalidCredentialsError()

        _audit_logger.info(
            "login_success user_id=%s username=%s ip=%s ua=%s",
            user["user_id"], username, source_ip, user_agent,
        )
        token_data = {"sub": str(user["user_id"]), "role": user["role"]}
        return {
            "access_token": create_access_token(token_data),
            "refresh_token": create_refresh_token(token_data),
            "user_id": user["user_id"],
            "role": user["role"],
            "display_name": user["display_name"],
        }

    def refresh(
        self,
        *,
        refresh_token: str,
        source_ip: str | None = None,
        user_agent: str | None = None,
    ) -> dict:
        payload = decode_refresh_token(refresh_token)
        if payload is None:
            # A failed refresh is a defensive signal (stolen/replayed token,
            # clock skew, or key rotation), so record it on the audit channel
            # with the same shape as login_failed for cross-event analysis.
            _audit_logger.warning(
                "refresh_failed reason=invalid_token ip=%s ua=%s",
                source_ip, user_agent,
            )
            raise InvalidRefreshTokenError()

        jti = payload.get("jti")
        if jti:
            invalidate_refresh_token(jti)

        user = self._repo.find_by_id(int(payload["sub"]))
        if not user:
            _audit_logger.warning(
                "refresh_failed reason=user_not_found sub=%s ip=%s ua=%s",
                payload.get("sub"), source_ip, user_agent,
            )
            raise UserNotFoundError()

        _audit_logger.info(
            "refresh_success user_id=%s jti=%s ip=%s ua=%s",
            user["user_id"], jti, source_ip, user_agent,
        )
        token_data = {"sub": str(user["user_id"]), "role": user["role"]}
        return {
            "access_token": create_access_token(token_data),
            "refresh_token": create_refresh_token(token_data),
            "user_id": user["user_id"],
            "role": user["role"],
            "display_name": user["display_name"],
        }

    def logout(self, *, refresh_token: str) -> None:
        payload = decode_refresh_token(refresh_token)
        if payload and (jti := payload.get("jti")):
            invalidate_refresh_token(jti)

    def get_me(self, *, user_id: int) -> dict:
        user = self._repo.find_by_id(user_id)
        if not user:
            raise UserNotFoundError()
        user.pop("password_hash", None)
        return user
