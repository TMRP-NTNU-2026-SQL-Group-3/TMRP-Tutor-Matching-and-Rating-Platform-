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

        hashed = hash_password(password)

        if self._repo.find_by_username(username):
            raise DuplicateUsernameError()

        return self._repo.register_user(
            username=username,
            password_hash=hashed,
            display_name=display_name,
            role=role,
            phone=phone,
            email=email,
        )

    def login(self, *, username: str, password: str) -> dict:
        user = self._repo.find_by_username(username)
        if not user or not verify_password(password, user["password_hash"]):
            raise InvalidCredentialsError()

        token_data = {"sub": str(user["user_id"]), "role": user["role"]}
        return {
            "access_token": create_access_token(token_data),
            "refresh_token": create_refresh_token(token_data),
            "user_id": user["user_id"],
            "role": user["role"],
            "display_name": user["display_name"],
        }

    def refresh(self, *, refresh_token: str) -> dict:
        payload = decode_refresh_token(refresh_token)
        if payload is None:
            raise InvalidRefreshTokenError()

        if jti := payload.get("jti"):
            invalidate_refresh_token(jti)

        user = self._repo.find_by_id(int(payload["sub"]))
        if not user:
            raise UserNotFoundError()

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
