import logging
from datetime import datetime, timedelta, timezone

from huey import crontab

from app.shared.infrastructure.config import settings
from app.shared.infrastructure.database import get_connection, release_connection
from app.worker import huey

logger = logging.getLogger("app.tasks.scheduled")


@huey.periodic_task(crontab(hour="3", minute="0"))
@huey.lock_task("lock-expired-reviews")
def lock_expired_reviews():
    """Daily at 03:00, lock reviews older than `review_lock_days` so they
    can no longer be edited by their author."""
    logger.info("Start locking expired reviews")
    conn = get_connection()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=settings.review_lock_days)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE reviews SET is_locked = TRUE "
                "WHERE created_at < %s AND (is_locked = FALSE OR is_locked IS NULL)",
                (cutoff,),
            )
        except Exception:
            logger.exception("lock_expired_reviews: cursor.execute failed")
            raise
        count = cursor.rowcount
        conn.commit()
        logger.info("Locked %d expired reviews", count)
    finally:
        release_connection(conn)


# Bug #11: GC the refresh_token_blacklist table once a day so it does not
# grow unbounded.
@huey.periodic_task(crontab(hour="3", minute="30"))
@huey.lock_task("cleanup-refresh-token-blacklist")
def cleanup_refresh_token_blacklist():
    from app.shared.infrastructure.security import cleanup_expired_blacklist
    deleted = cleanup_expired_blacklist()
    logger.info("Removed %d expired refresh-token blacklist rows", deleted)


# rate_limit_hits grows fast under load. The request path triggers
# `_cleanup_expired` opportunistically, but quiet periods can leave it
# stale for a long time, so schedule a guaranteed daily sweep here.
@huey.periodic_task(crontab(hour="3", minute="45"))
@huey.lock_task("cleanup-rate-limit-hits")
def cleanup_rate_limit_hits():
    from app.middleware.rate_limit import _cleanup_expired
    deleted = _cleanup_expired()
    logger.info("Removed %d expired rate-limit rows", deleted)
