import logging
import threading
import uuid
from collections import OrderedDict
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.shared.infrastructure.config import settings

JWTError = jwt.PyJWTError

logger = logging.getLogger("app.security")

# Bug #11: The used refresh token JTI blacklist has been moved to PostgreSQL
# (refresh_token_blacklist table) so multi-worker deployments share state.
# An in-memory cache remains to reduce DB queries; DB is the source of truth,
# the cache is purely an optimisation.
# M-03: OrderedDict-backed LRU. The previous dict + linear expired-sweep could
# stay pinned at max size when a burst of logouts produced >N non-expired
# entries, turning every subsequent insert into an O(N) scan that freed
# nothing. LRU eviction caps work at O(1) per insert regardless of expiry.
_blacklist_cache: "OrderedDict[str, float]" = OrderedDict()
_jti_lock = threading.Lock()
_REFRESH_TOKEN_TTL_SECONDS = 7 * 24 * 3600  # matches refresh token lifetime
_CACHE_MAX_SIZE = 1000


def _get_pool():
    """延遲匯入避免循環依賴。"""
    from app.shared.infrastructure.database import _require_pool
    return _require_pool()


def hash_password(password: str) -> str:
    """將明碼密碼以 bcrypt 雜湊後回傳。"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """驗證明碼是否與 bcrypt 雜湊值相符。

    Non-bcrypt sentinels (e.g. the 'ANONYMIZED' marker left behind by the
    admin anonymization flow) make bcrypt.checkpw raise ValueError. Swallow
    that and return False so login attempts against an anonymized account
    produce a normal 401, not a 500 that leaks the account state.
    """
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


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


def _previous_key_active() -> bool:
    """True while the rotation grace window is still open.

    Config guarantees an expiry is set whenever a previous key is set, so a
    missing deadline here means rotation is disabled entirely.
    """
    if not settings.jwt_secret_key_previous:
        return False
    raw = settings.jwt_secret_key_previous_expires_at.strip()
    if not raw:
        return False
    try:
        deadline = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return False
    return datetime.now(timezone.utc) < deadline


def _decode_with_rotation(token: str) -> dict | None:
    """Verify with the current key; on failure and within the rotation grace
    window, retry with the previous key.

    Returns the payload or None. Purpose: during key rotation, tokens signed
    by the previous key remain verifiable so in-flight sessions aren't all
    evicted at once. New tokens are always signed with the current key.
    The grace window is bounded by JWT_SECRET_KEY_PREVIOUS_EXPIRES_AT so a
    retired key cannot stay trusted indefinitely.
    """
    # S-C1: explicit rejection of alg=none before decode so PyJWT's algorithm
    # allowlist check is not the sole line of defence against this attack class.
    try:
        header = jwt.get_unverified_header(token)
    except JWTError:
        logger.warning("JWT header decode failed — malformed token")
        return None
    if header.get("alg", "").lower() == "none":
        logger.warning("JWT with alg=none rejected")
        return None
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])
    except JWTError as primary_err:
        if not _previous_key_active():
            logger.warning("JWT decode failed: %s", type(primary_err).__name__)
            return None
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret_key_previous,
                algorithms=["HS256"],
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
        _blacklist_cache.move_to_end(jti)
        while len(_blacklist_cache) > _CACHE_MAX_SIZE:
            _blacklist_cache.popitem(last=False)


def is_refresh_token_blacklisted(jti: str) -> bool:
    """檢查 JTI 是否在黑名單中且尚未過期。優先讀本機快取，未命中查 DB。"""
    now_ts = datetime.now(timezone.utc).timestamp()

    with _jti_lock:
        expiry = _blacklist_cache.get(jti)
        if expiry is not None:
            if now_ts >= expiry:
                del _blacklist_cache[jti]
            else:
                _blacklist_cache.move_to_end(jti)
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

    # Populate the cache to accelerate subsequent checks.
    with _jti_lock:
        _blacklist_cache[jti] = float(row[0])
        _blacklist_cache.move_to_end(jti)
        while len(_blacklist_cache) > _CACHE_MAX_SIZE:
            _blacklist_cache.popitem(last=False)
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


def consume_reset_confirmation_jti(jti: str, ttl_minutes: int = 5) -> bool:
    """LOW-4: mark a reset-confirmation JTI as used. Returns True if the JTI
    was consumed by this call (first use), False if it was already burnt.

    The destructive ``/api/admin/reset/confirm`` endpoint must call this on
    EVERY attempt — success or failure — before proceeding, otherwise a
    stolen reset token would remain replayable for its 5-minute TTL.

    Re-uses the existing ``refresh_token_blacklist`` table: its schema (jti
    PK + expires_at) matches the single-use + TTL semantics we need here, and
    the regular ``cleanup_expired_blacklist`` task already trims it.
    """
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)
    pool_ref = _get_pool()
    conn = pool_ref.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO refresh_token_blacklist (jti, expires_at) VALUES (%s, %s) "
                "ON CONFLICT (jti) DO NOTHING",
                (jti, expires_at),
            )
            inserted = cur.rowcount == 1
        conn.commit()
        return inserted
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        pool_ref.putconn(conn)


def create_reset_confirmation_token(user_id: int, ttl_minutes: int = 5) -> str:
    """Short-lived token that binds a subsequent destructive admin action
    (e.g. ``/api/admin/reset/confirm``) to a specific admin user.

    Defence in depth beyond the regular access token: even if an access token
    is stolen, a reset requires the attacker to obtain this freshly-issued,
    user-bound, short-TTL token AND the admin's plaintext password.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": "reset",
        "exp": now + timedelta(minutes=ttl_minutes),
        "iat": now,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_reset_confirmation_token(token: str) -> dict | None:
    """Return the payload only if the token is a valid, unexpired reset token.
    Returns None otherwise — callers MUST NOT proceed on None."""
    payload = _decode_with_rotation(token)
    if payload is None:
        return None
    if payload.get("type") != "reset":
        logger.warning("Non-reset token supplied to reset confirmation endpoint")
        return None
    return payload


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
