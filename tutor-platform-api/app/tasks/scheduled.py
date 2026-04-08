import logging
from datetime import datetime, timedelta, timezone

from huey import crontab

from app.config import settings
from app.database import get_connection
from app.utils.access_bits import to_access_bit
from app.worker import huey

logger = logging.getLogger("app.tasks.scheduled")


def _ensure_is_locked_column(conn) -> None:
    """若 Reviews 表尚未有 is_locked 欄位則新增（既有資料庫的遷移）。"""
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT TOP 1 is_locked FROM Reviews")
    except Exception:
        cursor.execute("ALTER TABLE Reviews ADD COLUMN is_locked BIT")
        cursor.execute("UPDATE Reviews SET is_locked = ?", (to_access_bit(False),))
        conn.commit()
        logger.info("已新增 is_locked 欄位至 Reviews")


@huey.periodic_task(crontab(hour="3", minute="0"))
@huey.lock_task("check-expired-reviews")
def check_expired_reviews():
    """每日凌晨 3 點將超過 review_lock_days 天編輯期限的評價設為鎖定。"""
    logger.info("開始檢查過期評價")
    conn = get_connection()
    try:
        _ensure_is_locked_column(conn)
        cutoff = datetime.now(timezone.utc) - timedelta(days=settings.review_lock_days)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE Reviews SET is_locked = ? "
            "WHERE created_at < ? AND (is_locked = ? OR is_locked IS NULL)",
            (to_access_bit(True), cutoff, to_access_bit(False)),
        )
        count = cursor.rowcount
        conn.commit()
        logger.info("已鎖定 %d 筆過期評價", count)
    finally:
        conn.close()
