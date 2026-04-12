import logging
from datetime import datetime, timedelta, timezone

from huey import crontab

from app.shared.infrastructure.config import settings
from app.shared.infrastructure.database import get_connection, release_connection
from app.worker import huey

logger = logging.getLogger("app.tasks.scheduled")


@huey.periodic_task(crontab(hour="3", minute="0"))
@huey.lock_task("check-expired-reviews")
def check_expired_reviews():
    """每日凌晨 3 點將超過 review_lock_days 天編輯期限的評價設為鎖定。"""
    logger.info("開始檢查過期評價")
    conn = get_connection()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=settings.review_lock_days)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reviews SET is_locked = TRUE "
            "WHERE created_at < %s AND (is_locked = FALSE OR is_locked IS NULL)",
            (cutoff,),
        )
        count = cursor.rowcount
        conn.commit()
        logger.info("已鎖定 %d 筆過期評價", count)
    finally:
        release_connection(conn)


# Bug #11: refresh_token_blacklist 表的過期條目每日清理一次，避免無限增長
@huey.periodic_task(crontab(hour="3", minute="30"))
@huey.lock_task("cleanup-refresh-token-blacklist")
def cleanup_refresh_token_blacklist():
    from app.shared.infrastructure.security import cleanup_expired_blacklist
    deleted = cleanup_expired_blacklist()
    logger.info("已清除 %d 筆過期 refresh token 黑名單", deleted)
