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
    PasswordReusedError,
    UserNotFoundError,
)
from .ports import IUserRepository

# L-03: dedicated audit channel so "who logged in from where and when" can be
# reconstructed after the fact. Child of the "app" logger so it inherits the
# rotating JSON file handler set up in setup_logger(). Never log the submitted
# password or issued tokens — the log file is not a credential store.
_audit_logger = logging.getLogger("app.audit")

# SEC-4: pre-computed dummy hash used so verify_password always runs on the
# login path, regardless of whether the username exists. Without this, fast
# returns for unknown usernames leak account existence via response timing.
_DUMMY_HASH = hash_password("timing-normalization-placeholder-value")


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
        # S-M2: strip CR/LF and cap length to prevent log injection and unbounded growth.
        user_agent = (user_agent or "").replace("\r", "").replace("\n", "")[:256]
        user = self._repo.find_by_username(username)
        check_hash = user["password_hash"] if user else _DUMMY_HASH
        password_ok = verify_password(password, check_hash)
        if not user or not password_ok:
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
        user_agent = (user_agent or "").replace("\r", "").replace("\n", "")[:256]
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

    def get_me(self, *, user_id: int) -> dict:
        user = self._repo.find_by_id(user_id)
        if not user:
            raise UserNotFoundError()
        user.pop("password_hash", None)
        return user

    def update_me(self, *, user_id: int, fields: dict) -> dict:
        updated = self._repo.update_me(user_id, fields=fields)
        if updated is None:
            return self.get_me(user_id=user_id)
        updated.pop("password_hash", None)
        return updated

    def change_password(self, *, user_id: int, current_password: str, new_password: str) -> None:
        user = self._repo.find_by_id(user_id)
        if not user or not verify_password(current_password, user["password_hash"]):
            raise InvalidCredentialsError()
        # SEC-06: reject reuse of the current password or any of the last 5 stored.
        all_prior = [user["password_hash"]] + self._repo.get_recent_password_hashes(user_id, limit=5)
        if any(verify_password(new_password, h) for h in all_prior):
            raise PasswordReusedError()
        new_hash = hash_password(new_password)
        self._repo.save_password_history(user_id, user["password_hash"])
        self._repo.update_password(user_id, password_hash=new_hash)
