"""Reusable Pydantic validators/Annotated types for request schemas.

Centralised so that empty-string / null / trim handling is consistent
across bounded contexts instead of each router reinventing it inline.
"""

from typing import Annotated

from pydantic import BeforeValidator


def _empty_str_to_none(v):
    """Collapse empty or whitespace-only strings into ``None``.

    Used so the DB stores NULL consistently and unique indexes do not
    treat ``""`` as a distinct value.
    """
    if isinstance(v, str) and not v.strip():
        return None
    return v


def _strip_non_empty(v):
    """Trim whitespace; reject strings that become empty after trimming."""
    if not isinstance(v, str):
        return v
    stripped = v.strip()
    if not stripped:
        raise ValueError("不可為空白")
    return stripped


# Optional string field: empty/whitespace input is normalised to None.
OptionalStr = Annotated[str | None, BeforeValidator(_empty_str_to_none)]

# Required string field: auto-trimmed, rejected if empty after trimming.
TrimmedStr = Annotated[str, BeforeValidator(_strip_non_empty)]
