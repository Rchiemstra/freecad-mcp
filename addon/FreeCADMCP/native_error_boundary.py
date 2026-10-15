"""Existing native errors admitted only within a native repair postcondition."""
from __future__ import annotations

import re

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


class MissingSourceRepair:
    def __init__(self, document: Any, baseline: NativeErrorBaseline) -> None:
        self.document = document
        self.baseline = baseline
        self.sources = {
            match.group(0)
            for _, detail, _ in baseline.values()
            for match in re.finditer(r"Document '[^']+' not found in '[^']+'", detail)
        }
        self.bindings = {
            id(obj): (obj, tuple(getattr(obj, "ExpressionEngine", ()) or ()))
            for obj in getattr(document, "Objects", ())
        }

        self.values = {
            key: {path: self._bound_value(obj, path) for path, _ in bindings}
            for key, (obj, bindings) in self.bindings.items()
        }

    @staticmethod
    def _bound_value(obj: Any, path: str) -> str | None:
        evaluate = getattr(obj, "evalExpression", None)
        if callable(evaluate):
            try:
                return str(evaluate(path))
            except Exception:
                pass
        return None

    def bindings_preserved(self) -> bool:
        for obj in getattr(self.document, "Objects", ()):
            bindings = tuple(getattr(obj, "ExpressionEngine", ()) or ())
            previous = self.bindings.get(id(obj))
            if bindings and (previous is None or previous[0] is not obj
                             or any(binding not in previous[1] for binding in bindings)):
                return False
            # A typed edit may change a cleared datum, but must not overwrite
            # a value still driven by a surviving unresolved binding.
            if any(self._bound_value(obj, path) != self.values[id(obj)].get(path)
                   for path, _ in bindings):
                return False
        return True

    def accepts_failure(self, result: Any) -> bool:
        if not self.sources or not isinstance(result, dict):
            return False
        if result.get("status") != "RecomputeFailed" or result.get("committed") is not False:
            return False
        detail = str(result.get("message", ""))
        prefix = "document recompute reported an object error: "
        if not detail.startswith(prefix):
            return False
        # Every failed node must be explained by the same absent sources or
        # by a dependency that already failed at the captured native boundary.
        errors = re.split(r", [A-Za-z_][\w]* \(", detail[len(prefix):])
        known_names = {str(getattr(obj, "Name", "")) for obj, _, _ in self.baseline.values()}
        return all(any(source in error for source in self.sources)
                   or any("dependency did not commit: " + name in error for name in known_names)
                   for error in errors)

    def settle(self, validate: Any) -> None:
        self.document.recompute()
        current = capture_native_error_baseline(self.document)
        for key, (obj, detail, state) in current.items():
            previous = self.bindings.get(key)
            bindings = tuple(getattr(obj, "ExpressionEngine", ()) or ())
            if (previous is not None and previous[0] is obj
                    and all(binding in previous[1] for binding in bindings)
                    and any(source in detail for source in self.sources)):
                # Removing one failed ancestor can expose another existing
                # binding's missing-source diagnostic on the same native node.
                self.baseline[key] = (obj, detail, state)
        with native_error_validation_scope(self.document, self.baseline, deferred=True):
            known = {key for key, (obj, _, _) in current.items()
                     if existing_native_error_unchanged(self.document, obj)}
            pending = dict(current)
            while pending:
                admitted = []
                for key, (obj, detail, state) in pending.items():
                    if key in known or (key in self.bindings and any(id(source) in known and detail ==
                            "dependency did not commit: " + str(getattr(source, "Name", ""))
                            for source in getattr(obj, "OutList", ()))):
                        self.baseline[key] = (obj, detail, state)
                        known.add(key)
                        admitted.append(key)
                if not admitted:
                    break
                for key in admitted:
                    del pending[key]
            for key in known:
                purge = getattr(current[key][0], "purgeTouched", None)
                if callable(purge):
                    purge()
        with native_error_validation_scope(self.document, self.baseline):
            if validate(self.document) is False:
                raise RuntimeError("Missing-source repair postcondition failed after recompute")


def _missing_source_error_objects(document: Any) -> tuple[Any, ...]:
    errors = capture_native_error_baseline(document)
    known = {key for key, (_, detail, _) in errors.items()
             if re.search(r"Document '[^']+' not found in '[^']+'", detail)}
    if not known:
        return ()
    while True:
        added = {key for key, (obj, detail, _) in errors.items() if key not in known
                 and any(id(source) in known and detail ==
                         "dependency did not commit: " + str(getattr(source, "Name", ""))
                         for source in getattr(obj, "OutList", ()))}
        if not added:
            break
        known.update(added)
    if known != errors.keys():
        return ()
    return tuple(errors[key][0] for key in known)


def terminal_missing_source_state(document: Any) -> bool:
    errors = _missing_source_error_objects(document)
    if not errors:
        return False
    known = {id(obj) for obj in errors}
    pending = list(getattr(document, "Objects", ()))
    visited: set[int] = set()
    while pending:
        obj = pending.pop()
        if id(obj) in visited:
            continue
        visited.add(id(obj))
        if not _native_work_settled(obj):
            return False
        if id(obj) not in known:
            state = _error_state(obj)
            execute = getattr(obj, "MustExecute", False)
            if (any("invalid" in item or "error" in item for item in state)
                    or bool(execute)):
                return False
        pending.extend(getattr(obj, "OutList", ()))
    return True


def settle_missing_source_history(document: Any) -> None:
    # Called only immediately after the authoritative history recompute.
    # Retire retry touches on proven native source failures, never unrelated
    # work or dirty spreadsheet cells. Later fresh touches block history again.
    errors = _missing_source_error_objects(document)
    if not errors:
        return
    known = {id(obj) for obj in errors}
    for obj in getattr(document, "Objects", ()):
        if id(obj) not in known and (not _native_work_settled(obj)
                                    or bool(getattr(obj, "MustExecute", False))):
            return
        dirty = getattr(obj, "getDirtyCells", None)
        if callable(dirty) and dirty():
            return
    for obj in errors:
        purge = getattr(obj, "purgeTouched", None)
        if callable(purge):
            purge()
