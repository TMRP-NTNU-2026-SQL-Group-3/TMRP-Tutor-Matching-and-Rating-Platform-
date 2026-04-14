"""JSON serializer for huey task payloads.

Replaces huey's default pickle-based serializer so that task arguments and
results stored on disk never contain pickle bytes. This closes the
deserialization-of-untrusted-data attack surface on any code path that reads
raw task payload bytes (for example, the admin task-status endpoint that
calls ``huey.storage.peek_data``).
"""

from __future__ import annotations

import json

from huey.serializer import Serializer
from huey.utils import Error


def _to_json_safe(obj):
    """Recursively rewrite huey-specific wrapper types into plain JSON shapes.

    ``Error`` is a tuple subclass, so json.dumps would otherwise emit it as
    a raw array and strip the type tag. Handle it explicitly before dispatch.
    BaseException is handled the same way because a task may place an
    exception on the result queue.
    """
    if isinstance(obj, Error):
        meta = obj[0] if len(obj) > 0 else {}
        return {"__huey_error__": True, "metadata": _to_json_safe(meta)}
    if isinstance(obj, BaseException):
        return {
            "__exception__": True,
            "type": type(obj).__name__,
            "message": str(obj),
        }
    if isinstance(obj, dict):
        return {str(k): _to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_json_safe(v) for v in obj]
    return obj


def _encode_default(obj):
    """Last-resort fallback for types json.dumps still cannot handle."""
    return str(obj)


class JSONSerializer(Serializer):
    """Huey Serializer that uses JSON instead of pickle.

    Binary payloads (bytes) are not supported; callers must pass JSON-safe
    primitives, dicts, and lists. Unknown types fall back to ``str(obj)``.
    """

    def _serialize(self, data):
        return json.dumps(
            _to_json_safe(data), default=_encode_default, ensure_ascii=False,
        ).encode("utf-8")

    def _deserialize(self, data):
        return json.loads(data.decode("utf-8"))
