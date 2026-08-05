"""Request-local authenticated RPC identity without document authority."""

from __future__ import annotations

import threading
from typing import Any

_local = threading.local()


def set_request_identity(**identity: Any) -> None:
    """Replace the current handler thread's transport/authentication identity."""

    _local.value = dict(identity)


def get_request_identity() -> dict[str, Any]:
    """Return a copy so callers cannot mutate another layer's request context."""

    return dict(getattr(_local, "value", {}))


def clear_request_identity() -> None:
    """Discard all request-local authentication material."""

    if hasattr(_local, "value"):
        del _local.value


__all__ = ["clear_request_identity", "get_request_identity", "set_request_identity"]
