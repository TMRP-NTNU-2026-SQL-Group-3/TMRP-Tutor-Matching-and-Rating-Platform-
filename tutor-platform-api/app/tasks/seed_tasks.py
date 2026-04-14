import logging

from app.shared.infrastructure.database import get_connection, release_connection
from app.worker import huey

logger = logging.getLogger("app.tasks.seed_tasks")


@huey.task(retries=3, retry_delay=10)
def generate_seed_data() -> dict:
    """Generate demo fixtures asynchronously.

    B8: the previous implementation committed after each staging block inside
    `run_seed`, so a mid-run failure could leave the database half-seeded.
    `run_seed` now stages all inserts without committing; this task owns the
    transaction boundary — a single commit on success, rollback on any
    exception before propagating for Huey retry.
    """
    logger.info("Seed task started")
    conn = get_connection()
    try:
        from seed.generator import run_seed

        try:
            result = run_seed(conn)
        except Exception:
            conn.rollback()
            logger.exception("Seed generation failed; rolled back")
            raise

        if result.get("skipped"):
            # run_seed short-circuited before any INSERT; nothing to commit.
            logger.info("Seed skipped: %s", result.get("message"))
            return result

        conn.commit()
        total = sum(v for v in result.values() if isinstance(v, int))
        logger.info("Seed committed (%d rows)", total)
        return result
    finally:
        release_connection(conn)
