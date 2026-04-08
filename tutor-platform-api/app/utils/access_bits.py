def to_access_bit(value: bool) -> int:
    """將 Python bool 轉換為 MS Access BIT 表示法（True → -1，False → 0）。"""
    return -1 if value else 0


def from_access_bit(value) -> bool:
    """將 MS Access BIT 欄位值安全轉換為 Python bool。

    MS Access BIT 可能返回 True/False、-1/0、1/0 等，
    視 ODBC 驅動版本而定。此函式統一處理所有情況。
    """
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    return int(value) != 0
