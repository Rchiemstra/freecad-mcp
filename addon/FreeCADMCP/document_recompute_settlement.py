"""Settle leftover ``mustExecute`` before native collaboration commits."""

from __future__ import annotations

import time
from typing import Any

try:
    from .rpc_server.gui_dispatch_ops.flush_gui_events import flush_gui_events
except ImportError:  # pragma: no cover - flat addon import path
    from rpc_server.gui_dispatch_ops.flush_gui_events import flush_gui_events


def _document_would_block_type() -> type[BaseException] | None:
    try:
        import FreeCAD

        candidate = getattr(FreeCAD, "DocumentWouldBlock", None)
        if isinstance(candidate, type) and issubclass(candidate, BaseException):
            return candidate
    except Exception:
        return None
    return None


def _handle_done(handle: Any) -> bool:
    done = getattr(handle, "done", None)
    if callable(done):
        return bool(done())
    status = getattr(handle, "status", None)
    if callable(status):
        snapshot = status()
        terminal = getattr(snapshot, "terminal", None)
        if callable(terminal):
            return bool(terminal())
    return False


def _settle_with_async_pump(document: object, *, force: bool) -> None:
    recompute_async = getattr(document, "recomputeAsync", None)
    if not callable(recompute_async):
        return
    handle = recompute_async(None, force) if force else recompute_async()
    if handle is None:
        return
    deadline = time.monotonic() + 360.0
    poll = getattr(handle, "poll", None)
    while time.monotonic() < deadline:
        if _handle_done(handle):
            break
        if callable(poll):
            poll()
        flush_gui_events(0)
        time.sleep(0.002)


def document_has_pending_must_execute(document: object) -> bool:
    """Return whether the document reports dirty recompute work."""

    must_execute = getattr(document, "mustExecute", None)
    if callable(must_execute):
        return bool(must_execute())
    getter = getattr(document, "getMutationReadiness", None)
    if callable(getter):
        try:
            readiness = getter()
        except Exception:
            return False
        if isinstance(readiness, dict):
            return bool(readiness.get("must_execute"))
    return False


def settle_document_must_execute(document: object, *, max_passes: int = 2) -> None:
    """Clear pending recompute work without blocking the GUI thread."""

    if not document_has_pending_must_execute(document):
        return

    would_block = _document_would_block_type()
    recompute = getattr(document, "recompute", None)
    if not callable(recompute):
        return

    for pass_index in range(max_passes):
        if not document_has_pending_must_execute(document):
            return
        force = pass_index > 0
        try:
            if force:
                recompute(None, True)
            else:
                recompute()
        except Exception as exc:
            if would_block is not None and isinstance(exc, would_block):
                _settle_with_async_pump(document, force=force)
            else:
                raise
        if not document_has_pending_must_execute(document):
            return

    purge = getattr(document, "purgeTouched", None)
    if callable(purge) and document_has_pending_must_execute(document):
        purge()
        if not document_has_pending_must_execute(document):
            return
        try:
            recompute()
        except Exception as exc:
            if would_block is not None and isinstance(exc, would_block):
                _settle_with_async_pump(document, force=False)
            else:
                raise


__all__ = ["document_has_pending_must_execute", "settle_document_must_execute"]
