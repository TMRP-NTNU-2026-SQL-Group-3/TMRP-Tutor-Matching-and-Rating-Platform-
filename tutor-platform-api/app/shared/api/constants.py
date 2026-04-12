"""API-wide constants shared across routers (pagination, etc.).

Kept separate from `Settings` because these are stable conventions of the
HTTP surface rather than deployment knobs.
"""

DEFAULT_PAGE_SIZE: int = 20
MAX_PAGE_SIZE: int = 100
