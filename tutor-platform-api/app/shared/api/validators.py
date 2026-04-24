"""Reusable Pydantic validators/Annotated types for request schemas.

Centralised so that empty-string / null / trim handling is consistent
across bounded contexts instead of each router reinventing it inline.
"""

from typing import Annotated

from pydantic import BeforeValidator


# I-16: Postgres text columns reject the U+0000 codepoint outright, and
# psycopg2 raises DataError on any string containing it — so a NUL byte
# slipped into any request field becomes a 500. Strip NULs before the rest
# of the validator pipeline runs. We drop them rather than reject the whole
# input because control characters in user-supplied text are almost always
# artefacts of upstream encoding bugs, not intent.
_NUL = chr(0)


def _scrub_null_bytes(v):
    if isinstance(v, str) and _NUL in v:
        return v.replace(_NUL, "")
    return v


def _empty_str_to_none(v):
    """Collapse empty or whitespace-only strings into ``None``.

    Used so the DB stores NULL consistently and unique indexes do not
    treat ``""`` as a distinct value.
    """
    v = _scrub_null_bytes(v)
    if isinstance(v, str) and not v.strip():
        return None
    return v


def _strip_non_empty(v):
    """Trim whitespace; reject strings that become empty after trimming."""
    v = _scrub_null_bytes(v)
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
