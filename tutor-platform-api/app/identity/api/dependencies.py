from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.shared.infrastructure.database import get_db  # noqa: F401 — re-exported for router imports
from app.shared.infrastructure.security import decode_access_token

# auto_error=False so a missing Bearer header is not an instant 401 — we
# check the HttpOnly cookie first (SEC-C02).
security_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
):
    # SEC-C02: prefer HttpOnly cookie, fall back to Bearer header (Swagger UI).
    token = request.cookies.get("access_token")
    if not token and credentials:
        token = credentials.credentials
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供認證 Token",
        )
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登入已過期或無效，請重新登入",
        )
    return payload


def is_admin(user: dict) -> bool:
    return user.get("role") == "admin"


def require_role(*roles: str):
    def checker(user: dict = Depends(get_current_user)):
        if user.get("role") not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="無權限執行此操作",
            )
        return user
    return checker


def get_auth_service(conn=Depends(get_db)):
    # Imported lazily to keep this module free of application-layer deps
    # for the common `get_db` / `get_current_user` import paths.
    from app.identity.domain.services import AuthService
    from app.identity.infrastructure.postgres_user_repo import PostgresUserRepository

    return AuthService(user_repo=PostgresUserRepository(conn))
