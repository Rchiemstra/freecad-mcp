"""§3.3 monkeypatch surfaces for instrumented_server."""

from __future__ import annotations

from typing import Any


def emit_event(*args: Any, **kwargs: Any) -> Any:
    """Delegate to the instrumented_server façade for test monkeypatching."""

    from ..instrumented_server import emit_event as facade_emit_event

    return facade_emit_event(*args, **kwargs)
