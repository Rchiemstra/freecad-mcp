from __future__ import annotations

import contextlib
import os
import threading
from typing import Any

from .internal_snapshot_save_state import _InternalSnapshotSaveState

_internal_snapshot_save_ctx = threading.local()

_internal_snapshot_save_ctx = threading.local()


def _normalized_snapshot_target(path: Any) -> str:
    value = os.fspath(path).strip()
    if not value:
        raise ValueError("internal snapshot target path must not be empty")
    return os.path.normcase(os.path.realpath(value))


def begin_internal_snapshot_save_scope(
    request_id: str,
    document: Any,
    target_path: Any,
) -> bool:
    """Mark only exact save callbacks from one trusted internal ``saveCopy``."""

    normalized_request_id = str(request_id or "").strip()
    if not normalized_request_id:
        raise ValueError("internal snapshot request_id must not be empty")
    if document is None:
        raise ValueError("internal snapshot document must not be empty")
    normalized_target = _normalized_snapshot_target(target_path)
    state = getattr(_internal_snapshot_save_ctx, "state", None)
    if state is None:
        state = _InternalSnapshotSaveState()
        _internal_snapshot_save_ctx.state = state
    if state.depth == 0:
        state.request_id = normalized_request_id
        state.document = document
        state.target_path = normalized_target
        state.violation = ""
    elif (
        state.request_id != normalized_request_id
        or state.document is not document
        or state.target_path != normalized_target
    ):
        state.violation = "nested internal snapshot save scope mismatch"
    state.depth += 1
    return not state.violation


def is_internal_snapshot_save(document: Any, target_path: Any) -> bool:
    """Return whether this exact synchronous save callback is internal."""

    state = getattr(_internal_snapshot_save_ctx, "state", None)
    if state is None or state.depth <= 0 or state.violation:
        return False
    try:
        normalized_target = _normalized_snapshot_target(target_path)
    except (TypeError, ValueError, OSError):
        return False
    return bool(
        state.document is document
        and state.target_path == normalized_target
    )


def end_internal_snapshot_save_scope(
    request_id: str,
    document: Any,
    target_path: Any,
) -> bool:
    """End an exact internal snapshot marker, failing closed on mismatch."""

    state = getattr(_internal_snapshot_save_ctx, "state", None)
    if state is None or state.depth <= 0:
        return False
    try:
        normalized_target = _normalized_snapshot_target(target_path)
    except (TypeError, ValueError, OSError):
        normalized_target = ""
    if (
        state.request_id != str(request_id or "").strip()
        or state.document is not document
        or state.target_path != normalized_target
    ):
        state.violation = "internal snapshot save scope teardown mismatch"
    state.depth -= 1
    valid = not state.violation
    if state.depth == 0:
        with contextlib.suppress(AttributeError):
            delattr(_internal_snapshot_save_ctx, "state")
    return valid
