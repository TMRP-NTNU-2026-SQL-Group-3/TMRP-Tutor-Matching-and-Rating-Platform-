import logging
import threading
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.shared.infrastructure.config import settings

logger = logging.getLogger("app.security")

# Bug #11: 已使用的 refresh token JTI 黑名單已遷移至 PostgreSQL
# (refresh_token_blacklist 表)，多 worker 部署下共享狀態。
# 仍保留 in-memory 快取以減少資料庫查詢；DB 為唯一真相，快取僅為效能優化。
_blacklist_cache: dict[str, float] = {}
_jti_lock = threading.Lock()
_REFRESH_TOKEN_TTL_SECONDS = 7 * 24 * 3600  # 7 天，與 refresh token 效期一致
_CACHE_MAX_SIZE = 1000


def _get_pool():
    """延遲匯入避免循環依賴。"""
    from app.shared.infrastructure.database import _require_pool
    return _require_pool()


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


def _decode_with_rotation(token: str) -> dict | None:
    """以目前的密鑰驗 token；若失敗、且設定了 JWT_SECRET_KEY_PREVIOUS，再以舊密鑰嘗試一次。

    回傳成功的 payload 或 None。設計目的：金鑰輪換期間，舊密鑰簽出的尚未過期 token
    仍能驗證，避免所有使用者一次被踢出。新發行的 token 一律以新密鑰簽。
    """
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as primary_err:
        if not settings.jwt_secret_key_previous:
            logger.warning("JWT decode failed: %s", type(primary_err).__name__)
            return None
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret_key_previous,
                algorithms=[settings.jwt_algorithm],
            )
            logger.info("JWT verified with previous key (rotation grace period)")
            return payload
        except JWTError as fallback_err:
            logger.warning(
                "JWT decode failed with both keys: primary=%s previous=%s",
                type(primary_err).__name__,
                type(fallback_err).__name__,
            )
            return None


def decode_access_token(token: str) -> dict | None:
    """解碼 JWT access token，拒絕 refresh token，失敗時回傳 None。"""
    payload = _decode_with_rotation(token)
    if payload is None:
        return None
    if payload.get("type") != "access":
        logger.warning("Rejected non-access token (type=%s)", payload.get("type"))
        return None
    return payload


def _cleanup_expired_cache() -> None:
    """清除快取中已過期的 JTI 條目（需在持有 _jti_lock 時呼叫）。"""
    now = datetime.now(timezone.utc).timestamp()
    expired = [jti for jti, exp in _blacklist_cache.items() if now >= exp]
    for jti in expired:
        del _blacklist_cache[jti]


def invalidate_refresh_token(jti: str) -> None:
    """將 refresh token 的 JTI 加入黑名單。先寫入 DB（共享真相），再更新本機快取。

    DB 寫入失敗時拋出例外——拒絕「以為登出成功但其實 token 仍可用」的偽安全狀態。
    """
    expires_at_ts = datetime.now(timezone.utc).timestamp() + _REFRESH_TOKEN_TTL_SECONDS
    expires_at = datetime.fromtimestamp(expires_at_ts, tz=timezone.utc)

    pool_ref = _get_pool()
    conn = pool_ref.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO refresh_token_blacklist (jti, expires_at) VALUES (%s, %s) "
                "ON CONFLICT (jti) DO UPDATE SET expires_at = EXCLUDED.expires_at",
                (jti, expires_at),
            )
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        pool_ref.putconn(conn)

    with _jti_lock:
        _blacklist_cache[jti] = expires_at_ts
        if len(_blacklist_cache) > _CACHE_MAX_SIZE:
            _cleanup_expired_cache()


def is_refresh_token_blacklisted(jti: str) -> bool:
    """檢查 JTI 是否在黑名單中且尚未過期。優先讀本機快取，未命中查 DB。"""
    now_ts = datetime.now(timezone.utc).timestamp()

    with _jti_lock:
        expiry = _blacklist_cache.get(jti)
        if expiry is not None:
            if now_ts >= expiry:
                del _blacklist_cache[jti]
            else:
                return True

    # 快取未命中：查 DB（多 worker 共享真相）
    pool_ref = _get_pool()
    conn = pool_ref.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT EXTRACT(EPOCH FROM expires_at) FROM refresh_token_blacklist "
                "WHERE jti = %s AND expires_at > NOW()",
                (jti,),
            )
            row = cur.fetchone()
        # 讀取查詢需 commit/rollback 結束交易，避免連線歸還時殘留
        conn.rollback()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        pool_ref.putconn(conn)

    if row is None:
        return False

    # 寫入快取以加速後續查詢
    with _jti_lock:
        _blacklist_cache[jti] = float(row[0])
    return True


def cleanup_expired_blacklist() -> int:
    """清除 DB 中已過期的黑名單條目（背景任務呼叫，回傳刪除筆數）。"""
    pool_ref = _get_pool()
    conn = pool_ref.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM refresh_token_blacklist WHERE expires_at <= NOW()")
            deleted = cur.rowcount
        conn.commit()
        return deleted or 0
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        pool_ref.putconn(conn)


def decode_refresh_token(token: str) -> dict | None:
    """解碼 JWT refresh token，僅接受 type=refresh，並拒絕已使用過的 token。"""
    payload = _decode_with_rotation(token)
    if payload is None:
        return None
    if payload.get("type") != "refresh":
        logger.warning("Non-refresh token used for refresh endpoint")
        return None
    jti = payload.get("jti")
    if jti and is_refresh_token_blacklisted(jti):
        logger.warning("Reuse of invalidated refresh token jti=%s", jti)
        return None
    return payload
