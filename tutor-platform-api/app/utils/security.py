import logging
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.config import settings

logger = logging.getLogger("app.security")

# 已使用的 refresh token JTI 黑名單（token rotation）
_used_refresh_jti: set[str] = set()


def hash_password(password: str) -> str:
    """將明碼密碼以 bcrypt 雜湊後回傳。"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """驗證明碼是否與 bcrypt 雜湊值相符。"""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """建立 JWT access token（短效期）。"""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.jwt_expire_minutes))
    to_encode.update({
        "exp": expire,
        "iat": now,
        "jti": str(uuid.uuid4()),
        "type": "access",
    })
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(data: dict) -> str:
    """建立 JWT refresh token（長效期，7 天）。"""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=7)
    to_encode.update({
        "exp": expire,
        "iat": now,
        "jti": str(uuid.uuid4()),
        "type": "refresh",
    })
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict | None:
    """解碼 JWT access token，拒絕 refresh token，失敗時回傳 None。"""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != "access":
            logger.warning("Rejected non-access token (type=%s)", payload.get("type"))
            return None
        return payload
    except JWTError as e:
        logger.warning("JWT decode failed: %s", type(e).__name__)
        return None


def invalidate_refresh_token(jti: str) -> None:
    """將 refresh token 的 JTI 加入黑名單，使其無法再次使用。"""
    _used_refresh_jti.add(jti)


def decode_refresh_token(token: str) -> dict | None:
    """解碼 JWT refresh token，僅接受 type=refresh，並拒絕已使用過的 token。"""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != "refresh":
            logger.warning("Non-refresh token used for refresh endpoint")
            return None
        jti = payload.get("jti")
        if jti and jti in _used_refresh_jti:
            logger.warning("Reuse of invalidated refresh token jti=%s", jti)
            return None
        return payload
    except JWTError as e:
        logger.warning("Refresh token decode failed: %s", type(e).__name__)
        return None
