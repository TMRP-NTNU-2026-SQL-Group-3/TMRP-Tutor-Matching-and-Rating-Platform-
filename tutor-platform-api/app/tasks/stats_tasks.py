import logging
import re
from datetime import datetime

from app.database import get_connection
from app.repositories.stats_repo import StatsRepository
from app.worker import huey

logger = logging.getLogger("app.tasks.stats_tasks")

_MONTH_RE = re.compile(r'^\d{4}-\d{2}$')


def _parse_month(month: str | None) -> tuple[int, int] | str:
    """解析月份字串，回傳 (year, mon) 或錯誤訊息字串。"""
    if month:
        if not _MONTH_RE.match(month):
            return "月份格式應為 YYYY-MM"
        try:
            year, mon = map(int, month.split("-"))
        except (ValueError, TypeError):
            return "月份格式應為 YYYY-MM"
        if not (1 <= mon <= 12):
            return "無效的月份值（1-12）"
        if not (2000 <= year <= 2100):
            return "無效的年份值（2000-2100）"
    else:
        now = datetime.now()
        year, mon = now.year, now.month
    return year, mon


@huey.task(retries=3, retry_delay=10)
def calculate_income_stats(user_id: int, month: str | None = None) -> dict:
    """非同步計算老師收入統計。"""
    logger.info("計算收入統計: user_id=%d, month=%s", user_id, month)
    conn = get_connection()
    try:
        repo = StatsRepository(conn)
        tutor = repo.get_tutor_by_user(user_id)
        if not tutor:
            return {"error": "找不到老師資料"}

        parsed = _parse_month(month)
        if isinstance(parsed, str):
            return {"error": parsed}
        year, mon = parsed

        tutor_id = tutor["tutor_id"]
        summary = repo.income_summary(tutor_id, year, mon)
        if summary is None:
            summary = {"total_hours": 0, "total_income": 0, "session_count": 0}
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
    except Exception:
        logger.exception("計算收入統計失敗")
        raise
    finally:
        conn.close()


@huey.task(retries=3, retry_delay=10)
def calculate_expense_stats(user_id: int, month: str | None = None) -> dict:
    """非同步計算家長支出統計。"""
    logger.info("計算支出統計: user_id=%d, month=%s", user_id, month)
    conn = get_connection()
    try:
        repo = StatsRepository(conn)

        parsed = _parse_month(month)
        if isinstance(parsed, str):
            return {"error": parsed}
        year, mon = parsed

        summary = repo.expense_summary(user_id, year, mon)
        if summary is None:
            summary = {"total_hours": 0, "total_expense": 0, "session_count": 0}
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
    except Exception:
        logger.exception("計算支出統計失敗")
        raise
    finally:
        conn.close()
