"""共用欄位名稱驗證與 CSV 值轉換工具。"""

import re

_SAFE_COLUMN_NAME = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def validate_column_name(col: str) -> bool:
    """檢查單一欄位名稱是否僅含合法識別字元。"""
    return bool(_SAFE_COLUMN_NAME.match(col))


def validate_columns(columns: list[str]) -> None:
    """驗證一批欄位名稱，不合法時拋出 ValueError。"""
    for col in columns:
        if not _SAFE_COLUMN_NAME.match(col):
            raise ValueError(f"不合法的欄位名稱：{col!r}")


def quote_columns(columns: list[str]) -> str:
    """將欄位名稱以雙引號引用組合（PostgreSQL 識別符引用方式）。"""
    return ", ".join(f'"{col}"' for col in columns)


def coerce_csv_value(val):
    """將 CSV 字串值轉換為適合 PostgreSQL 的型別。

    - None / 空字串 → None
    - 布林真值 ('True', 'true', '1', '-1') → True
    - 布林假值 ('False', 'false', '0') → False
    - 其他 → 原值
    """
    if val is None:
        return None
    if not val or val.strip() == "":
        return None
    if val in ('True', 'true', '1', '-1'):
        return True
    if val in ('False', 'false', '0'):
        return False
    return val
