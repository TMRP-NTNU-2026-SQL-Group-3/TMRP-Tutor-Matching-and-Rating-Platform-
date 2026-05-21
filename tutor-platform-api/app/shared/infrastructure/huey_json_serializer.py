"""JSON serializer for huey task payloads.

Replaces huey's default pickle-based serializer so that task arguments and
results stored on disk never contain pickle bytes. This closes the
deserialization-of-untrusted-data attack surface on any code path that reads
raw task payload bytes (for example, the admin task-status endpoint that
calls ``huey.storage.peek_data``).

Task messages are ``huey.registry.Message`` namedtuples. ``json.dumps`` would
flatten a namedtuple into a plain array, and ``json.loads`` would hand back a
bare ``list`` with no ``.name`` attribute -- which is exactly what breaks
``Registry.create_task``. Messages are therefore serialized inside a tagged
envelope so the namedtuple type (and its datetime fields, e.g. the ``eta`` set
on retried tasks) survives the round-trip.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from huey.registry import Message
from huey.serializer import Serializer
from huey.utils import Error

# Envelope tags. Each is the *sole* key of a one-element dict so a decoder can
# recognise it without ambiguity against ordinary task payloads.
_MESSAGE_TAG = "__huey_message__"
_DATETIME_TAG = "__datetime__"
_DATE_TAG = "__date__"
_TIMEDELTA_TAG = "__timedelta__"


def _to_json_safe(obj, tag_temporal: bool = False):
    """Recursively rewrite huey-specific types into plain JSON shapes.

    ``tag_temporal`` controls datetime handling. It is enabled only inside a
    ``Message`` subtree: huey needs ``eta`` / ``expires`` back as real
    datetimes, and a task may be called with datetime arguments. Task *results*
    keep the previous lossy behaviour (datetimes fall through to ``str``) so the
    admin task-status endpoint -- which decodes result payloads with its own
    ``json.loads`` -- never sees envelope tags.
    """
    if isinstance(obj, Message):
        # Tag the namedtuple so _from_json_safe can rebuild it. on_complete /
        # on_error may themselves be nested Messages, so recurse field by field.
        return {_MESSAGE_TAG: [_to_json_safe(v, True) for v in obj]}
    if isinstance(obj, Error):
        # Error is a tuple subclass, so json.dumps would otherwise emit it as a
        # raw array and strip the type tag. Handle it explicitly before dispatch.
        meta = obj[0] if len(obj) > 0 else {}
        return {"__huey_error__": True, "metadata": _to_json_safe(meta, tag_temporal)}
    if isinstance(obj, BaseException):
        # A task may place an exception on the result queue.
        return {
            "__exception__": True,
            "type": type(obj).__name__,
            "message": str(obj),
        }
    if tag_temporal and isinstance(obj, datetime):
        return {_DATETIME_TAG: obj.isoformat()}
    if tag_temporal and isinstance(obj, date):
        # datetime is a subclass of date, so this is reached only by pure dates.
        return {_DATE_TAG: obj.isoformat()}
    if tag_temporal and isinstance(obj, timedelta):
        return {_TIMEDELTA_TAG: obj.total_seconds()}
    if isinstance(obj, dict):
        return {str(k): _to_json_safe(v, tag_temporal) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_json_safe(v, tag_temporal) for v in obj]
    return obj


def _from_json_safe(obj):
    """Reverse of :func:`_to_json_safe` -- rebuild tagged envelopes."""
    if isinstance(obj, dict):
        if len(obj) == 1:
            if _MESSAGE_TAG in obj:
                return Message(*[_from_json_safe(v) for v in obj[_MESSAGE_TAG]])
            if _DATETIME_TAG in obj:
                return datetime.fromisoformat(obj[_DATETIME_TAG])
            if _DATE_TAG in obj:
                return date.fromisoformat(obj[_DATE_TAG])
            if _TIMEDELTA_TAG in obj:
                return timedelta(seconds=obj[_TIMEDELTA_TAG])
        return {k: _from_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_from_json_safe(v) for v in obj]
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
        obj = _from_json_safe(json.loads(data.decode("utf-8")))
        # Backward compatibility: payloads written before this serializer was
        # fixed stored the Message namedtuple as a bare JSON array, which
        # json.loads returns as a plain list that Registry.create_task cannot
        # use. Detect a top-level array shaped like a Message (12 fields, with
        # string id + name) and rebuild it so tasks already queued by an older
        # build still drain instead of erroring out and being discarded.
        if (
            isinstance(obj, list)
            and len(obj) == len(Message._fields)
            and isinstance(obj[0], str)
            and isinstance(obj[1], str)
        ):
            return Message(*obj)
        return obj
