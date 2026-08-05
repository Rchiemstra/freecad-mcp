from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from . import state
from .constants import (
    _AGENT_OWNED_STATES,
    _MUTATING_ACTION_NAMES,
    _MUTATING_ACTION_PREFIXES,
)
from .lease_view import _lease_view


def _comparison_forms(value: Any) -> set[str]:
    text = str(value or "").strip()
    if not text:
        return set()
    folded = text.replace("\\", "/").casefold()
    return {folded}


def _looks_like_canonical_path(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    normalized = text.replace("\\", "/")
    return bool(
        normalized.startswith("/")
        or normalized.startswith("//")
        or (len(normalized) >= 3 and normalized[1:3] == ":/")
    )


def _looks_like_session_uuid(value: Any) -> bool:
    try:
        uuid.UUID(str(value or "").strip())
    except (AttributeError, TypeError, ValueError):
        return False
    return True


def _lease_canonical_forms(view: Mapping[str, Any]) -> set[str]:
    values = [view.get("comparison_key"), view.get("canonical_path")]
    if not any(values) and _looks_like_canonical_path(view.get("doc_key")):
        values.append(view.get("doc_key"))
    forms: set[str] = set()
    for value in values:
        forms.update(_comparison_forms(value))
    return forms


def _lease_matches_hints(lease: Mapping[str, Any], hints: list[str]) -> bool:
    clean_hints = [str(hint).strip() for hint in hints if str(hint).strip()]
    if not clean_hints:
        return False
    view = _lease_view(lease)
    path_hints = [hint for hint in clean_hints if _looks_like_canonical_path(hint)]
    session_hints = [hint for hint in clean_hints if _looks_like_session_uuid(hint)]

    if path_hints or session_hints:
        if path_hints:
            wanted_paths: set[str] = set()
            for hint in path_hints:
                wanted_paths.update(_comparison_forms(hint))
            if not wanted_paths.intersection(_lease_canonical_forms(view)):
                return False
        if session_hints:
            session_uuid = str(view.get("document_session_uuid") or "").casefold()
            if not session_uuid or session_uuid not in {
                hint.casefold() for hint in session_hints
            }:
                return False
        return True

    wanted_names = {hint.casefold() for hint in clean_hints}
    actual_names = {
        str(value).casefold()
        for value in (view.get("doc_name"), view.get("filename"))
        if value
    }
    return bool(wanted_names.intersection(actual_names))


def _active_document_only_hints() -> list[str]:
    """Return identity hints for FreeCAD.ActiveDocument, excluding selection."""

    try:
        import FreeCAD

        document = getattr(FreeCAD, "ActiveDocument", None)
    except Exception:
        return []
    hints: list[str] = []
    for value in (
        getattr(document, "FileName", None),
        getattr(document, "Name", None),
    ):
        if value and str(value) not in hints:
            hints.append(str(value))
    return hints


def _agent_owns_active_document(
    leases: list[Mapping[str, Any]], hints: list[str] | None = None
) -> bool:
    active_hints = _active_document_only_hints() if hints is None else hints
    for lease in leases:
        if not _lease_matches_hints(lease, active_hints):
            continue
        if _lease_view(lease)["state"].upper() in _AGENT_OWNED_STATES:
            return True
    return False


def _action_object_name(action: Any) -> str:
    value = getattr(action, "objectName", "")
    try:
        value = value() if callable(value) else value
    except RuntimeError:
        return ""
    return str(value or "")


def _is_known_mutating_action(action: Any) -> bool:
    name = _action_object_name(action)
    return name in _MUTATING_ACTION_NAMES or name.startswith(_MUTATING_ACTION_PREFIXES)


def _disable_mutating_actions(actions: list[Any]) -> None:
    for action in actions:
        if not _is_known_mutating_action(action):
            continue
        key = id(action)
        try:
            enabled = bool(action.isEnabled())
            if key not in state._shared_state.deterred_actions and enabled:
                state._shared_state.deterred_actions[key] = action
            if enabled:
                action.setEnabled(False)
        except RuntimeError:
            state._shared_state.deterred_actions.pop(key, None)


def _restore_mutating_actions() -> None:
    for key, action in list(state._shared_state.deterred_actions.items()):
        try:
            action.setEnabled(True)
        except RuntimeError:
            pass
        finally:
            state._shared_state.deterred_actions.pop(key, None)


def _update_command_deterrence(
    leases: list[Mapping[str, Any]],
    *,
    hints: list[str] | None = None,
    actions: list[Any] | None = None,
) -> bool:
    """Disable/restore known mutating QActions for the active leased document."""

    blocked = _agent_owns_active_document(leases, hints=hints)
    if actions is None:
        try:
            import FreeCADGui
            from PySide import QtWidgets

            main = FreeCADGui.getMainWindow()
            actions = list(main.findChildren(QtWidgets.QAction)) if main else []
        except Exception:
            actions = []

    if blocked:
        _disable_mutating_actions(actions)
        return True

    _restore_mutating_actions()
    return False


def _active_document_hints() -> list[str]:
    """Return selected-document hints followed by active-document hints."""

    hints: list[str] = []
    try:
        import FreeCADGui

        for selected in FreeCADGui.Selection.getSelection():
            document = getattr(selected, "Document", None)
            for value in (
                getattr(document, "FileName", None),
                getattr(document, "Name", None),
                getattr(selected, "DocumentName", None),
            ):
                if value and value not in hints:
                    hints.append(str(value))
    except Exception:
        pass
    try:
        import FreeCAD

        document = getattr(FreeCAD, "ActiveDocument", None)
        for value in (
            getattr(document, "FileName", None),
            getattr(document, "Name", None),
        ):
            if value and value not in hints:
                hints.append(str(value))
    except Exception:
        pass
    return hints


def _select_preferred_lease(
    leases: list[Mapping[str, Any]], hints: list[str] | None = None
) -> Mapping[str, Any] | None:
    """Prefer the selected/active document, then the most urgent state."""

    if not leases:
        return None
    document_hints = _active_document_hints() if hints is None else hints
    strong_hints = [
        hint
        for hint in document_hints
        if _looks_like_canonical_path(hint) or _looks_like_session_uuid(hint)
    ]
    matching_hints = strong_hints or document_hints
    for hint in matching_hints:
        for lease in leases:
            if _lease_matches_hints(lease, [hint]):
                return lease

    priority = {
        "USER_INTERVENED": 0,
        "LOCKED_ERROR": 1,
        "UNLOCKED_DIRTY": 2,
        "STALE": 3,
        "ACQUIRING": 4,
        "CANCELLING": 5,
    }
    return min(leases, key=lambda item: priority.get(_lease_view(item)["state"], 10))
