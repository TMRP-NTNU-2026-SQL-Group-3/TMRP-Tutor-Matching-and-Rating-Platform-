def to_access_bit(value: bool) -> int:
    """將 Python bool 轉換為 MS Access BIT 表示法（True → -1，False → 0）。"""
    return -1 if value else 0
