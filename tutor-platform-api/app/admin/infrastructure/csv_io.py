"""CSV read/write helpers used by the admin import/export flows."""

from __future__ import annotations

import csv
import io
from pathlib import Path


def parse_csv(content: str) -> list[dict]:
    """Parse a CSV byte-string and normalise header whitespace."""
    reader = csv.DictReader(io.StringIO(content))
    rows = list(reader)
    return [{(h or "").strip(): v for h, v in row.items()} for row in rows]


def write_csv(file_path: str, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    """Write rows to a CSV file under the sandboxed `data/` directory.

    Raises ValueError if the target path escapes the allowed base directory.
    """
    if not rows:
        return
    path = Path(file_path).resolve()
    allowed_base = Path("data").resolve()
    if not path.is_relative_to(allowed_base):
        raise ValueError(f"不允許的檔案路徑：{file_path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
