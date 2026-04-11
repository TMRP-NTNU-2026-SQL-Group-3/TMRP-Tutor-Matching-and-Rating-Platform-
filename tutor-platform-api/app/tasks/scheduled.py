import logging
from datetime import datetime, timedelta, timezone

from huey import crontab

from app.config import settings
from app.database import get_connection, release_connection
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
