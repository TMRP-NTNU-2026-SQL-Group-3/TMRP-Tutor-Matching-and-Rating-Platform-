import logging
from datetime import datetime

from app.database import get_connection
from app.repositories.stats_repo import StatsRepository
from app.worker import huey

logger = logging.getLogger("app.tasks.stats_tasks")


@huey.task()
def calculate_income_stats(user_id: int, month: str | None = None) -> dict:
    """非同步計算老師收入統計。"""
    logger.info("計算收入統計: user_id=%d, month=%s", user_id, month)
    conn = get_connection()
    try:
        repo = StatsRepository(conn)
        tutor = repo.get_tutor_by_user(user_id)
        if not tutor:
            return {"error": "找不到老師資料"}

        if month:
            year, mon = map(int, month.split("-"))
        else:
            now = datetime.now()
            year, mon = now.year, now.month

        tutor_id = tutor["tutor_id"]
        summary = repo.income_summary(tutor_id, year, mon)
        breakdown = repo.income_breakdown(tutor_id, year, mon)

        for row in breakdown:
            row["hours"] = float(row["hours"] or 0)
            row["income"] = float(row["income"] or 0)

        return {
            "year": year,
            "month": mon,
            "total_hours": float(summary["total_hours"] or 0),
            "total_income": float(summary["total_income"] or 0),
            "session_count": int(summary["session_count"] or 0),
            "breakdown": breakdown,
        }
    except Exception as e:
        logger.error("計算收入統計失敗: %s", str(e))
        return {"error": str(e)}
    finally:
        conn.close()


@huey.task()
def calculate_expense_stats(user_id: int, month: str | None = None) -> dict:
    """非同步計算家長支出統計。"""
    logger.info("計算支出統計: user_id=%d, month=%s", user_id, month)
    conn = get_connection()
    try:
        repo = StatsRepository(conn)

        if month:
            year, mon = map(int, month.split("-"))
        else:
            now = datetime.now()
            year, mon = now.year, now.month

        summary = repo.expense_summary(user_id, year, mon)
        breakdown = repo.expense_breakdown(user_id, year, mon)

        for row in breakdown:
            row["hours"] = float(row["hours"] or 0)
            row["expense"] = float(row["expense"] or 0)

        return {
            "year": year,
            "month": mon,
            "total_hours": float(summary["total_hours"] or 0),
            "total_expense": float(summary["total_expense"] or 0),
            "session_count": int(summary["session_count"] or 0),
            "breakdown": breakdown,
        }
    except Exception as e:
        logger.error("計算支出統計失敗: %s", str(e))
        return {"error": str(e)}
    finally:
        conn.close()
