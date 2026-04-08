import csv
from pathlib import Path

from app.config import settings


def _get_allowed_base() -> Path:
    """以 access_db_path 的父目錄作為允許的檔案存取根目錄。"""
    return Path(settings.access_db_path).resolve().parent


def read_csv(file_path: str) -> list[dict]:
    """讀取 CSV 並回傳 list of dict。"""
    path = Path(file_path).resolve()
    allowed_base = _get_allowed_base()
    if not path.is_relative_to(allowed_base):
        raise ValueError(f"不允許的檔案路徑：{file_path}")
    with path.open("r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return list(reader)


def write_csv(file_path: str, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    """將 list of dict 寫入 CSV 檔案。"""
    if not rows:
        return
    path = Path(file_path).resolve()
    allowed_base = _get_allowed_base()
    if not path.is_relative_to(allowed_base):
        raise ValueError(f"不允許的檔案路徑：{file_path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
