"""Existing native errors admitted only within a native repair postcondition."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

NativeErrorBaseline = dict[int, tuple[object, str, tuple[str, ...]]]
_ACTIVE_ERRORS: ContextVar[tuple[object, NativeErrorBaseline, bool] | None] = ContextVar(
    "native_error_validation_boundary", default=None,
)

_GENERIC_STATUS = frozenset({"", "error", "invalid", "touched", "valid", "freezed"})


def _status_text(reader: Any, argument: Any | None = None) -> str:
    if not callable(reader):
        return ""
    try:
        value = reader() if argument is None else reader(argument)
    except Exception:
        return ""
    return str(value or "").strip()


def _object_error_detail(obj: Any) -> str:
    """FreeCAD stores the recompute exception on the object status string."""

    texts = [_status_text(getattr(obj, "getStatusString", None))]
    document = getattr(obj, "Document", None)
    if document is None:
        getter = getattr(obj, "getDocument", None)
        document = getter() if callable(getter) else None
    texts.append(_status_text(getattr(document, "getErrorDescription", None), obj))
    for text in texts:
        if text.lower() not in _GENERIC_STATUS:
            return text
    return ""


def _error_state(obj: Any) -> tuple[str, ...]:
    # Expanded is tree presentation, independent of the native model error.
    return tuple(sorted(str(item).lower() for item in getattr(obj, "State", ())
                        if str(item).lower() not in {"touched", "expanded"}))


def capture_native_error_baseline(document: Any) -> NativeErrorBaseline:
    errors: NativeErrorBaseline = {}
    for obj in getattr(document, "Objects", ()):
        state = _error_state(obj)
        # DocumentObjectPy exposes ObjectStatus::Error as "Invalid".
        if any("error" in item or "invalid" in item for item in state) and not hasattr(obj, "Proxy"):
            detail = _object_error_detail(obj)
            if detail:
                errors[id(obj)] = (obj, detail, state)
    return errors


@contextmanager
def native_error_validation_scope(
    document: object, baseline: NativeErrorBaseline, *, deferred: bool = False,
) -> Iterator[None]:
    token = _ACTIVE_ERRORS.set((document, baseline, deferred))
    try:
        yield
    finally:
        _ACTIVE_ERRORS.reset(token)


def _native_work_settled(obj: Any) -> bool:
    state = {str(item).lower() for item in getattr(obj, "State", ())}
    if state.intersection({"touched", "dirty", "recompute", "recompute2"}):
        return False
    # Sheet.MustExecute also includes settled cell errors. Read the native
    # dirty cache separately so terminal diagnostics cannot hide fresh cells.
    dirty_cells = getattr(obj, "getDirtyCells", None)
    if callable(dirty_cells):
        try:
            return not bool(dirty_cells())
        except Exception:
            return False
    return True


def existing_native_error_unchanged(document: object, obj: Any) -> bool:
    active = _ACTIVE_ERRORS.get()
    if active is None or active[0] is not document or hasattr(obj, "Proxy"):
        return False
    baseline = active[1].get(id(obj))
    return (baseline is not None and baseline[0] is obj
            and (active[2] or _native_work_settled(obj))
            and baseline[1] == _object_error_detail(obj) and baseline[2] == _error_state(obj))
