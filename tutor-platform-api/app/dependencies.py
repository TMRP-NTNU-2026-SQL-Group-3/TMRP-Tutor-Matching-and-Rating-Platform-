from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.database import get_db  # noqa: F401 — re-exported for router imports
from app.utils.security import decode_access_token

security_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
):
    """從 JWT Token 解碼目前登入的使用者資訊。"""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供認證 Token",
        )
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登入已過期或無效，請重新登入",
        )
    return payload


def is_admin(user: dict) -> bool:
    """判斷目前使用者是否具有 admin 角色。"""
    return user.get("role") == "admin"


def require_role(*roles: str):
    """建立一個依賴項，限制僅指定角色可存取。"""

    def checker(user: dict = Depends(get_current_user)):
        if user.get("role") not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="無權限執行此操作",
            )
        return user

    return checker
