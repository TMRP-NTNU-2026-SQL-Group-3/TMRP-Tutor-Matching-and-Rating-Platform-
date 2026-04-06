import logging

from app.database import get_connection
from app.worker import huey

logger = logging.getLogger("app.tasks.seed_tasks")


@huey.task(retries=3, retry_delay=10)
def generate_seed_data() -> dict:
    """非同步生成假資料。"""
    logger.info("開始生成假資料")
    conn = get_connection()
    try:
        from seed.generator import run_seed

        result = run_seed(conn)
        if result.get("skipped"):
            logger.info("假資料生成已跳過: %s", result.get("message"))
        else:
            total = sum(v for v in result.values() if isinstance(v, int))
            logger.info("已生成 %d 筆假資料", total)
        return result
    except Exception:
        logger.exception("假資料生成失敗")
        raise
    finally:
        conn.close()
