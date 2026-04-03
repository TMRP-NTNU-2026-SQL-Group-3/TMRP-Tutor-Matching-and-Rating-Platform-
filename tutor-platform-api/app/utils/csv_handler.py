import csv
from pathlib import Path


def read_csv(file_path: str) -> list[dict]:
    """讀取 CSV 並回傳 list of dict。"""
    path = Path(file_path)
    with path.open("r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return list(reader)


def write_csv(file_path: str, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    """將 list of dict 寫入 CSV 檔案。"""
    if not rows:
        return
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
