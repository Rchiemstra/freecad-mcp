"""Persistent, token-safe GUI status for per-document MCP leases.

PySide and FreeCAD are imported lazily so this module remains usable in the
headless test suite.  Closing the detail dock never releases a lease and never
hides the permanent status-bar indicator.
"""

from __future__ import annotations

import os
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

try:
    from document_state import (
        document_modified_or_dirty,
        document_modified_state,
        require_document_modified,
    )
except ImportError:
    from addon.FreeCADMCP.document_state import (
        document_modified_or_dirty,
        document_modified_state,
        require_document_modified,
    )

_installed = False
_status_widget = None
_dock_widget = None
_refresh_timer = None
_refresh_bridge = None
_deterred_actions: dict[int, Any] = {}

_LOCAL_SAVE_GUI_TIMEOUT = 120.0

_AGENT_OWNED_STATES = frozenset(
    {
        "ACQUIRING",
        "LOCKED_IDLE",
        "LOCKED_EDITING",
        "LOCKED_RECOMPUTING",
        "LOCKED_SAVING",
        "LOCKED_ERROR",
        "CANCELLING",
        "RELEASING",
        "STALE",
    }
)
_MUTATING_ACTION_NAMES = frozenset(
    {
        "Std_Undo",
        "Std_Redo",
        "Std_Cut",
        "Std_Paste",
        "Std_Delete",
        "Std_DuplicateSelection",
        "Std_Save",
        "Std_SaveAll",
        "Std_SaveAs",
        "Std_SaveCopy",
        "Std_Revert",
        "Std_CloseActiveWindow",
        "Std_CloseAllWindows",
        "Std_Import",
        "Std_MergeProjects",
        "Std_Edit",
        "Std_Transform",
        "Std_TransformManip",
        "Std_DlgMacroRecord",
        "Std_DlgMacroExecute",
        "Std_DlgMacroExecuteDirect",
        "Std_MacroExecute",
        "Std_MacroRecord",
    }
)
_MUTATING_ACTION_PREFIXES = (
    "PartDesign_",
    "Sketcher_",
    "Part_",
    "Draft_",
    "Arch_",
    "BIM_",
)

_SECRET_FIELD_NAMES = frozenset(
    {
        "token",
        "lease_token",
        "session_token",
        "rpc_session_token",
        "auth_secret",
        "secret",
        "token_fingerprint",
    }
)


def _format_elapsed(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {sec}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


def _bounded_text(value: Any, *, limit: int = 160) -> str:
    """Return single-line diagnostic text suitable for the UI."""

    text = " ".join(str(value or "").split())
    if len(text) > limit:
        return text[: max(0, limit - 1)] + "…"
    return text


def _collect_secret_values(value: Any) -> set[str]:
    secrets: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).casefold()
            sensitive = (
                normalized in _SECRET_FIELD_NAMES
                or normalized.endswith("_token")
                or (
                    "fingerprint" in normalized
                    and normalized != "profile_path_fingerprint"
                )
            )
            if sensitive and isinstance(item, str) and item:
                secrets.add(item)
            else:
                secrets.update(_collect_secret_values(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            secrets.update(_collect_secret_values(item))
    return secrets


def _redact_secrets(value: Any, *, _known_secrets: set[str] | None = None) -> Any:
    """Recursively remove credential material before it reaches a widget.

    V1 records still contain a raw ``token`` and v2 sidecar-shaped records may
    contain a token fingerprint.  Neither representation is useful to a human
    operator, so both are removed at the registry/UI boundary rather than only
    being omitted from a particular tooltip.
    """

    known_secrets = (
        _collect_secret_values(value) if _known_secrets is None else _known_secrets
    )
    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key).casefold()
            if normalized in _SECRET_FIELD_NAMES or normalized.endswith("_token"):
                continue
            if "fingerprint" in normalized and normalized != "profile_path_fingerprint":
                continue
            redacted[str(key)] = _redact_secrets(item, _known_secrets=known_secrets)
        return redacted
    if isinstance(value, (list, tuple)):
        return [_redact_secrets(item, _known_secrets=known_secrets) for item in value]
    if isinstance(value, str):
        redacted_text = value
        for secret in known_secrets:
            redacted_text = redacted_text.replace(secret, "[redacted]")
        return redacted_text
    return value


def _timestamp_age(value: Any, *, now: float | None = None) -> float:
    """Return the non-negative age of a unix or RFC3339 timestamp."""

    current = time.time() if now is None else float(now)
    if isinstance(value, (int, float)):
        return max(0.0, current - float(value))
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return max(0.0, current - parsed.timestamp())
        except (TypeError, ValueError, OverflowError):
            pass
    return 0.0


def _lease_view(lease: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize legacy and schema-v2 public records for presentation."""

    safe = _redact_secrets(lease)
    document = safe.get("document") if isinstance(safe.get("document"), Mapping) else {}
    local_document = (
        safe.get("local_document")
        if isinstance(safe.get("local_document"), Mapping)
        else {}
    )
    display_document = (
        local_document
        if safe.get("source") == "foreign_recovery" and local_document
        else document
    )
    owner = safe.get("owner") if isinstance(safe.get("owner"), Mapping) else {}
    lease_meta = safe.get("lease") if isinstance(safe.get("lease"), Mapping) else {}
    document_state = (
        safe.get("document_state")
        if isinstance(safe.get("document_state"), Mapping)
        else {}
    )

    canonical_path = display_document.get("canonical_path")
    comparison_key = display_document.get("comparison_key")
    doc_key = (
        safe.get("doc_key")
        or canonical_path
        or display_document.get("session_uuid")
        or safe.get("document_session_uuid")
        or ""
    )
    doc_name = safe.get("doc_name") or display_document.get("name") or ""
    filename = doc_name or doc_key or "(unknown document)"
    if str(doc_key).casefold().endswith(".fcstd"):
        filename = Path(str(doc_key)).name

    state = safe.get("state") or lease_meta.get("state") or "LOCKED_IDLE"
    error = document_state.get("error") or safe.get("error_info")
    baseline = document_state.get("baseline")
    snapshot_id = document_state.get("snapshot_id")
    baseline_available = bool(
        baseline
        or snapshot_id
        or safe.get("baseline_hash")
        or safe.get("baseline_mtime") is not None
    )

    return {
        "record_id": str(
            safe.get("lease_id")
            or display_document.get("session_uuid")
            or safe.get("document_session_uuid")
            or doc_key
        ),
        "is_v2": bool(
            safe.get("schema_version") == 2
            or (isinstance(safe.get("document"), Mapping) and lease_meta)
        ),
        "source": str(safe.get("source") or "local"),
        "lease_id": safe.get("lease_id"),
        "document_session_uuid": (
            display_document.get("session_uuid") or safe.get("document_session_uuid")
        ),
        "canonical_path": str(canonical_path or ""),
        "comparison_key": str(comparison_key or ""),
        "doc_key": str(doc_key),
        "doc_name": str(doc_name),
        "filename": str(filename),
        "state": str(getattr(state, "value", state)),
        "client": owner.get("client") or safe.get("client") or "(unknown)",
        "agent_id": owner.get("agent_id") or safe.get("agent_id") or "",
        "instance_id": owner.get("mcp_instance_id") or safe.get("instance_id") or "",
        "pid": owner.get("mcp_pid") or safe.get("pid"),
        "host": owner.get("hostname") or safe.get("host") or "",
        "current_operation": (
            lease_meta.get("current_operation") or safe.get("current_operation") or ""
        ),
        "task": lease_meta.get("task_summary") or safe.get("task_description") or "",
        "acquired_at": lease_meta.get("acquired_at") or safe.get("acquired_at"),
        "last_heartbeat": (
            lease_meta.get("last_heartbeat_at") or safe.get("last_heartbeat")
        ),
        "dirty": bool(document_state.get("dirty", safe.get("document_dirty", False))),
        "user_intervened": bool(
            document_state.get("user_intervened", safe.get("user_intervened", False))
        ),
        "baseline_available": baseline_available,
        "file_baseline_available": bool(baseline),
        "snapshot_id": str(snapshot_id or ""),
        "error": error if isinstance(error, Mapping) else None,
    }


def _state_presentation(state: str) -> tuple[str, str, str]:
    """Return ``(icon, color, human label)`` for every v2 state family."""

    normalized = str(state or "").upper()
    if normalized in {"LOCKED_SAVING", "RELEASING"}:
        return (
            "◆",
            "#7b3fb5",
            {
                "LOCKED_SAVING": "Saving / verifying",
                "RELEASING": "Finalizing",
            }[normalized],
        )
    if normalized in {"ACQUIRING", "CANCELLING", "STALE"}:
        return (
            "⌛",
            "#a15c00",
            {
                "ACQUIRING": "Preparing lease",
                "CANCELLING": "Cancelling",
                "STALE": "Stale lease",
            }[normalized],
        )
    if normalized in {
        "LOCKED_ERROR",
        "USER_INTERVENED",
        "UNLOCKED_DIRTY",
    }:
        return (
            "⚠",
            "#b42318",
            {
                "LOCKED_ERROR": "Lease error",
                "USER_INTERVENED": "User intervened",
                "UNLOCKED_DIRTY": "Unlocked with unsaved changes",
            }[normalized],
        )
    if any(
        marker in normalized
        for marker in ("ERROR", "INTERVENED", "DIRTY", "MISSING", "MALFORMED")
    ):
        return "⚠", "#b42318", "Lease coordination error"
    if "NETWORK" in normalized or "LOWER_ASSURANCE" in normalized:
        return "⌛", "#a15c00", "Lower-assurance lease"
    if normalized == "UNLOCKED_SAVED":
        return "✓", "#287a3d", "Saved and unlocked"
    return (
        "🔒",
        "#2764c5",
        {
            "LOCKED_EDITING": "Agent editing",
            "LOCKED_RECOMPUTING": "Agent recomputing",
            "LOCKED_IDLE": "Agent lease idle",
        }.get(normalized, "Agent lease"),
    )


def _lease_lines(lease: Mapping[str, Any]) -> tuple[str, str]:
    """Return token-safe ``(status_bar_text, tooltip)``."""

    view = _lease_view(lease)
    _icon, _color, state_label = _state_presentation(view["state"])
    operation = _bounded_text(view["current_operation"])
    text = f"{state_label} {view['filename']}"
    if operation:
        text += f" — {operation}"
    if view["dirty"]:
        text += " — Unsaved"

    owner_label = _bounded_text(view["agent_id"] or view["client"])
    acquired_age = _timestamp_age(view["acquired_at"])
    heartbeat_age = _timestamp_age(view["last_heartbeat"])
    tip_lines = [
        f"Document: {_bounded_text(view['filename'], limit=260)}",
        f"Document name: {_bounded_text(view['doc_name']) or '(unknown)'}",
        f"State: {_bounded_text(view['state'])}",
        f"Source: {_bounded_text(view['source']).replace('_', ' ')}",
        f"Agent/client: {owner_label or '(unknown)'}",
        f"MCP instance: {_bounded_text(view['instance_id']) or '(unknown)'}",
        "PID: "
        f"{view['pid'] or '(unknown)'}  "
        f"host: {_bounded_text(view['host']) or '(unknown)'}",
        f"Operation: {operation or '(idle)'}",
        f"Task: {_bounded_text(view['task']) or '(none)'}",
        f"Held for: {_format_elapsed(acquired_age)}",
        f"Last heartbeat: {_format_elapsed(heartbeat_age)} ago",
        f"Unsaved: {'yes' if view['dirty'] else 'no'}",
        "Recovery baseline: "
        f"{'available' if view['baseline_available'] else 'not available'}",
    ]
    if view["error"]:
        tip_lines.append(
            "Error: "
            + _bounded_text(
                view["error"].get("code") or view["error"].get("message") or "unknown"
            )
        )
    return text, "\n".join(tip_lines)


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

    # Strong identity assertions are authoritative.  A same-named or
    # same-basename document must not match after either assertion disagrees.
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

    # No comparable path/session identity was supplied (normally an unsaved
    # document).  Fall back to exact diagnostic names only; never derive a
    # basename from a canonical path.
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


def _update_command_deterrence(
    leases: list[Mapping[str, Any]],
    *,
    hints: list[str] | None = None,
    actions: list[Any] | None = None,
) -> bool:
    """Disable/restore known mutating QActions for the active leased document.

    This is a normal-GUI deterrent, not a mutation veto.  Python console,
    macros, third-party commands, and native code remain observer-fenced after
    the fact as documented by the lease security model.
    """

    global _deterred_actions
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
        for action in actions:
            if not _is_known_mutating_action(action):
                continue
            key = id(action)
            try:
                enabled = bool(action.isEnabled())
                if key not in _deterred_actions and enabled:
                    _deterred_actions[key] = action
                if enabled:
                    action.setEnabled(False)
            except RuntimeError:
                _deterred_actions.pop(key, None)
        return True

    for key, action in list(_deterred_actions.items()):
        try:
            action.setEnabled(True)
        except RuntimeError:
            pass
        finally:
            _deterred_actions.pop(key, None)
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


def _active_leases() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()

    service = _v2_lease_service()
    if service is not None:
        try:
            effective_list = getattr(
                service, "list_effective_records", service.list_records
            )
            for payload in effective_list():
                safe = _redact_secrets(payload)
                record_id = _lease_view(safe)["record_id"]
                result.append(safe)
                seen.add(record_id)
            for payload in _foreign_shadow_leases(service):
                safe = _redact_secrets(payload)
                record_id = _lease_view(safe)["record_id"]
                if record_id not in seen:
                    result.append(safe)
                    seen.add(record_id)
        except Exception:
            # A temporarily unavailable v2 service must not prevent legacy
            # status from continuing to render.
            pass

    try:
        from document_lock import list_leases

        for record in list_leases():
            if hasattr(record, "to_public_dict"):
                payload = record.to_public_dict()
            elif hasattr(record, "to_dict"):
                payload = record.to_dict()
            elif isinstance(record, Mapping):
                payload = dict(record)
            else:
                continue
            safe = _redact_secrets(payload)
            record_id = _lease_view(safe)["record_id"]
            if record_id not in seen:
                result.append(safe)
                seen.add(record_id)
    except Exception:
        pass
    return result


def _foreign_shadow_leases(service: Any) -> list[dict[str, Any]]:
    """Read token-free sidecar shadows for currently open documents."""

    freecad = sys.modules.get("FreeCAD")
    list_documents = getattr(freecad, "listDocuments", None)
    if not callable(list_documents):
        return []

    effective_list = getattr(service, "list_effective_records", service.list_records)
    local_sessions = {
        str(
            item.get("local_document", {}).get("session_uuid")
            or item.get("document", {}).get("session_uuid")
            or ""
        )
        for item in effective_list()
        if isinstance(item, Mapping)
    }
    shadows: list[dict[str, Any]] = []
    for document in list_documents().values():
        try:
            identity = service.identity_service.resolve(
                {"document_name": str(getattr(document, "Name", "") or "")}
            )
            if identity.session_uuid in local_sessions or not identity.canonical_path:
                continue
            sidecar = Path(f"{identity.canonical_path}.freecad-mcp.lock")
            if not os.path.lexists(sidecar):
                continue
            try:
                record = service.sidecar_store.read(sidecar)
                payload = record.to_public_dict()
                payload["source"] = "foreign_sidecar"
                shadows.append(payload)
            except Exception as exc:
                # Never surface unvalidated JSON.  The synthetic shadow keeps
                # the selected document visibly blocked and red.
                shadows.append(
                    {
                        "schema_version": 2,
                        "record_kind": "freecad-mcp-document-lease-shadow",
                        "lease_id": f"unknown:{identity.session_uuid}",
                        "generation": 0,
                        "source": "unknown_sidecar",
                        "document": identity.to_dict(),
                        "owner": {},
                        "lease": {
                            "state": "SIDECAR_MALFORMED",
                            "current_operation": "Recovery required",
                        },
                        "document_state": {
                            "dirty": document_modified_or_dirty(document),
                            "dirty_state_known": (
                                document_modified_state(document) is not None
                            ),
                            "baseline": None,
                            "error": {
                                "code": "SIDECAR_UNKNOWN",
                                "message": _bounded_text(exc, limit=300),
                            },
                        },
                    }
                )
        except Exception:
            continue
    return shadows


def _v2_lease_service() -> Any | None:
    """Return the running addon's v2 service without triggering an import."""

    # The indicator is installed by InitGui after rpc_server has normally been
    # loaded.  Looking only in sys.modules avoids a circular/heavy import during
    # startup and keeps the module headless-importable in tests.
    for module_name in (
        "rpc_server.rpc_server",
        "addon.FreeCADMCP.rpc_server.rpc_server",
    ):
        module = sys.modules.get(module_name)
        service = getattr(module, "document_lease_service", None)
        if service is not None:
            return service
    package = sys.modules.get("rpc_server")
    module = getattr(package, "rpc_server", None) if package is not None else None
    service = getattr(module, "document_lease_service", None)
    if service is not None:
        return service
    return None


def _live_document_for_view(view: Mapping[str, Any], service: Any) -> Any | None:
    """Resolve the exact live document selected in the dock."""

    freecad = sys.modules.get("FreeCAD")
    list_documents = getattr(freecad, "listDocuments", None)
    if not callable(list_documents):
        return None
    expected_uuid = str(view.get("document_session_uuid") or "")
    for document in list_documents().values():
        try:
            identity = service.identity_service.resolve(
                {"document_name": str(getattr(document, "Name", "") or "")}
            )
            if expected_uuid and identity.session_uuid == expected_uuid:
                return document
        except Exception:
            continue
    return None


def _local_recovery_capabilities(
    lease: Mapping[str, Any], document: Any | None
) -> dict[str, bool]:
    """Return token-free availability for selected-document GUI actions."""

    view = _lease_view(lease)
    state = view["state"].upper()
    local = view["source"] == "local"
    imported_foreign = view["source"] == "foreign_recovery"
    live = document is not None
    v2_local = local and view["is_v2"] and live
    return {
        "takeover": bool(
            (local or imported_foreign)
            and (live or (local and not view["is_v2"]))
            and state in _AGENT_OWNED_STATES
        ),
        "keep_dirty": bool(
            v2_local
            and state == "USER_INTERVENED"
            and document_modified_state(document) is True
        ),
        "save_and_clear": bool(
            v2_local
            and state in {"USER_INTERVENED", "UNLOCKED_DIRTY"}
            and view["canonical_path"]
            and view["file_baseline_available"]
        ),
        "restore_baseline": bool(
            v2_local
            and state in {"USER_INTERVENED", "UNLOCKED_DIRTY"}
            and view["snapshot_id"]
        ),
    }


def _confirmed_foreign_takeover(
    lease: Mapping[str, Any],
    service: Any,
    document: Any,
    *,
    reason: str,
) -> Mapping[str, Any]:
    """Apply the already-confirmed selected-document foreign takeover."""

    view = _lease_view(lease)
    if view["source"] != "foreign_recovery" or not view["is_v2"]:
        raise RuntimeError("the selected record is not imported foreign authority")
    session_uuid = str(view.get("document_session_uuid") or "")
    if not session_uuid:
        raise RuntimeError("the selected foreign recovery has no local document UUID")
    live_identity = service.identity_service.inspect_registered_document(
        session_uuid, document
    )
    document_dirty = require_document_modified(document)
    record = service.confirmed_takeover_foreign_recovery(
        {"document_session_uuid": session_uuid},
        live_document=live_identity,
        confirmed=True,
        document_dirty=document_dirty,
        reason=reason,
    )
    return record.to_public_dict()


def _acknowledge_selected_dirty(
    lease: Mapping[str, Any], service: Any, document: Any
) -> Mapping[str, Any]:
    """Apply the confirmed local keep-dirty action to one exact document."""

    view = _lease_view(lease)
    session_uuid = view["document_session_uuid"]
    if not session_uuid or view["source"] != "local" or not view["is_v2"]:
        raise RuntimeError(
            "keep-dirty is available only for a local v2 recovery record"
        )
    if require_document_modified(document) is not True:
        raise RuntimeError("FreeCAD does not report the selected document as dirty")
    return service.acknowledge_local_dirty(
        {"document_session_uuid": session_uuid},
        document_dirty=True,
        reason="Confirmed local GUI keep-dirty acknowledgement",
    ).to_public_dict()


def _runtime_save_components() -> tuple[Any, Any, Any, Any, Any]:
    for module_name in (
        "rpc_server.rpc_server",
        "addon.FreeCADMCP.rpc_server.rpc_server",
    ):
        module = sys.modules.get(module_name)
        if module is None:
            continue
        save = getattr(module, "save_service", None)
        expectations = getattr(module, "_saved_document_expectations", None)
        validator = getattr(module, "_validate_saved_document_worker", None)
        discard = getattr(module, "_discard_terminal_snapshot", None)
        dispatcher = getattr(module, "gui_dispatcher", None)
        if (
            save is not None
            and callable(expectations)
            and callable(validator)
            and callable(getattr(dispatcher, "submit", None))
        ):
            return save, expectations, validator, discard, dispatcher
    raise RuntimeError(
        "verified local save is unavailable because the typed save/worker service "
        "and GUI dispatcher are not running"
    )


def _submit_local_save_gui(dispatcher: Any, task: Callable[[], Any]) -> Any:
    """Submit one bounded save phase to the already-running GUI dispatcher."""

    submit = getattr(dispatcher, "submit", None)
    if not callable(submit):
        raise RuntimeError("the FreeCAD GUI dispatcher is not running")
    return submit(
        task,
        timeout=_LOCAL_SAVE_GUI_TIMEOUT,
        request_id=f"local-save-{uuid.uuid4()}",
    )


def _inspect_local_save_document_gui(
    service: Any,
    document: Any,
    *,
    session_uuid: str,
) -> Any:
    """Re-resolve the exact live proxy from inside a GUI-dispatched phase."""

    identity_service = getattr(service, "identity_service", None)
    inspect = getattr(identity_service, "inspect_registered_document", None)
    if not callable(inspect):
        raise RuntimeError("live document identity validation is unavailable")
    identity = inspect(session_uuid, document)
    if str(getattr(identity, "session_uuid", "") or "") != session_uuid:
        raise RuntimeError("the live document session identity changed")
    return identity


def _verified_local_save_and_clear(
    lease: Mapping[str, Any],
    service: Any,
    document: Any,
    *,
    save_service: Any | None = None,
    expectation_builder: Any | None = None,
    worker_validator: Any | None = None,
    snapshot_discarder: Any | None = None,
    gui_dispatcher: Any | None = None,
) -> Mapping[str, Any]:
    """Run the phased local recovery save from a non-GUI orchestration thread.

    Expensive source hashing, archive inspection, and matching-worker reopen
    validation stay on the caller.  The running :class:`GuiDispatcher` owns
    only live-document inspection, ``Document.save()``, final lightweight
    revalidation, GUI modified-state capture, and the lease CAS clear.
    """

    view = _lease_view(lease)
    session_uuid = view["document_session_uuid"]
    if not session_uuid or view["source"] != "local" or not view["is_v2"]:
        raise RuntimeError("save-and-clear is available only for a local v2 record")
    state = view["state"].upper()
    if state not in {"USER_INTERVENED", "UNLOCKED_DIRTY"}:
        raise RuntimeError("take over the selected document before saving and clearing")

    current = service.get({"document_session_uuid": session_uuid})
    baseline_payload = (
        current.get("document_state", {}).get("baseline")
        if isinstance(current, Mapping)
        else None
    )
    if not baseline_payload:
        raise RuntimeError(
            "the selected document has no saved baseline; guarded Save As recovery is required"
        )
    try:
        from document_lease.model import FileBaseline
    except ImportError:
        from addon.FreeCADMCP.document_lease.model import FileBaseline

    expected_baseline = FileBaseline.from_dict(baseline_payload)
    if expected_baseline is None:
        raise RuntimeError("the selected document baseline is invalid")
    current_document = current.get("document", {})
    expected_path = (
        current_document.get("canonical_path")
        if isinstance(current_document, Mapping)
        else None
    )
    if not expected_path:
        raise RuntimeError(
            "the selected document has no current saved path; guarded Save As recovery is required"
        )
    if save_service is None:
        (
            save_service,
            expectation_builder,
            worker_validator,
            snapshot_discarder,
            gui_dispatcher,
        ) = _runtime_save_components()
    if not callable(expectation_builder) or not callable(worker_validator):
        raise RuntimeError("matching-worker save validation is unavailable")
    if not callable(getattr(gui_dispatcher, "submit", None)):
        raise RuntimeError("the FreeCAD GUI dispatcher is not running")

    expected_comparison_key = (
        current_document.get("comparison_key")
        if isinstance(current_document, Mapping)
        else None
    )

    def capture_gui_context() -> Mapping[str, Any]:
        identity = _inspect_local_save_document_gui(
            service,
            document,
            session_uuid=session_uuid,
        )
        live_path = str(getattr(identity, "canonical_path", "") or "")
        live_comparison = str(getattr(identity, "comparison_key", "") or "")
        if not live_path:
            raise RuntimeError(
                "the live document no longer has a saved path; guarded Save As "
                "recovery is required"
            )
        if expected_comparison_key:
            if live_comparison != str(expected_comparison_key):
                raise RuntimeError("the live document path changed before save")
        elif os.path.normcase(os.path.realpath(live_path)) != os.path.normcase(
            os.path.realpath(str(expected_path))
        ):
            raise RuntimeError("the live document path changed before save")
        return {
            "source_path": live_path,
            "document_name": str(
                getattr(identity, "name", "")
                or getattr(document, "Name", "")
                or view["doc_name"]
            ),
            "validation_expectations": expectation_builder(document),
        }

    gui_context = _submit_local_save_gui(gui_dispatcher, capture_gui_context)

    # Full compare-before-save hashing intentionally runs on this non-Qt
    # orchestration thread.
    preflight = save_service.prepare_save(
        gui_context["source_path"],
        expected_baseline=expected_baseline,
        expected_path=str(expected_path),
        validation_profile="local-recovery",
    )

    invocation = _submit_local_save_gui(
        gui_dispatcher,
        lambda: save_service.invoke_save_gui(document, preflight),
    )

    expected_document = gui_context["validation_expectations"]
    document_name = str(gui_context["document_name"])

    def validate_in_worker(path: str, profile: str) -> Mapping[str, Any]:
        return worker_validator(path, document_name, profile, expected_document)

    # Archive/hash and matching-worker verification intentionally run off Qt.
    saved = save_service.verify_saved_file(
        invocation,
        domain_validator=validate_in_worker,
    )

    def promote_and_clear_gui() -> Mapping[str, Any]:
        live_identity = _inspect_local_save_document_gui(
            service,
            document,
            session_uuid=session_uuid,
        )
        live_comparison = str(getattr(live_identity, "comparison_key", "") or "")
        saved_comparison = str(getattr(invocation, "comparison_key", "") or "")
        if saved_comparison and live_comparison != saved_comparison:
            raise RuntimeError("the live document path changed after save validation")
        save_service.revalidate_saved_document_gui(document, saved)
        document_modified = require_document_modified(document)
        return service.complete_local_save_and_clear(
            {"document_session_uuid": session_uuid},
            verified_baseline=saved.baseline,
            # SaveService.verify_saved_file returned this baseline only after
            # archive and independent matching-worker/domain validation.
            baseline_validated=True,
            document_modified=document_modified,
        )

    terminal = _submit_local_save_gui(gui_dispatcher, promote_and_clear_gui)
    # Snapshot deletion is filesystem-only and therefore remains off Qt.
    if callable(snapshot_discarder):
        snapshot_discarder(terminal)
    return {"save": saved.to_dict(), "release": terminal}


def _start_verified_local_save_and_clear_async(
    lease: Mapping[str, Any],
    service: Any,
    document: Any,
    *,
    completion_emit: Callable[[Mapping[str, Any]], None],
    thread_factory: Callable[..., Any] = threading.Thread,
    **pipeline_dependencies: Any,
) -> Any:
    """Start the local save pipeline and emit one thread-safe outcome.

    The GUI passes a Qt signal's ``emit`` method here.  Its receiver is wired
    with ``QueuedConnection`` so this worker never manipulates a widget.
    ``thread_factory`` keeps launch and completion behavior directly testable.
    """

    if not callable(completion_emit):
        raise TypeError("completion_emit must be callable")

    def run() -> None:
        try:
            result = _verified_local_save_and_clear(
                lease,
                service,
                document,
                **pipeline_dependencies,
            )
        except Exception as exc:
            outcome: Mapping[str, Any] = {
                "ok": False,
                "error": str(exc),
                "error_type": type(exc).__name__,
            }
        else:
            outcome = {"ok": True, "result": result}
        try:
            completion_emit(outcome)
        except RuntimeError:
            # Qt may destroy the bridge while FreeCAD is closing.  The lease
            # lifecycle itself has already completed or failed conservatively.
            pass

    worker = thread_factory(
        target=run,
        name="FreeCADMCP-local-save-recovery",
        daemon=True,
    )
    worker.start()
    return worker


def _connect_queued_qt_signal(
    signal: Any, slot: Callable[..., Any], qt_core: Any
) -> None:
    """Connect a cross-thread completion signal with an explicit Qt queue."""

    try:
        queued = qt_core.Qt.ConnectionType.QueuedConnection
    except AttributeError:
        queued = qt_core.Qt.QueuedConnection
    signal.connect(slot, queued)


def _runtime_restore_components() -> tuple[Any, Any, Any, Any]:
    """Resolve the bounded in-place restore implementation from the live addon."""

    for module_name in (
        "rpc_server.rpc_server",
        "addon.FreeCADMCP.rpc_server.rpc_server",
    ):
        module = sys.modules.get(module_name)
        if module is None:
            continue
        dispatcher = getattr(module, "gui_dispatcher", None)
        path_resolver = getattr(module, "recovery_snapshot_path", None)
        restore = getattr(module, "restore_snapshot_in_place_gui", None)
        validator = getattr(module, "validate_document_invariants", None)
        if (
            callable(getattr(dispatcher, "submit", None))
            and callable(path_resolver)
            and callable(restore)
            and callable(validator)
        ):
            return dispatcher, path_resolver, restore, validator
    raise RuntimeError(
        "baseline restore is unavailable because the lease snapshot service "
        "and GUI dispatcher are not running"
    )


def _record_public_dict(record: Any) -> Mapping[str, Any]:
    if isinstance(record, Mapping):
        return record
    render = getattr(record, "to_public_dict", None)
    if callable(render):
        value = render()
        if isinstance(value, Mapping):
            return value
    raise RuntimeError("lease service returned an invalid recovery record")


def _restore_local_baseline(
    lease: Mapping[str, Any],
    service: Any,
    document: Any,
    *,
    gui_dispatcher: Any | None = None,
    snapshot_path_resolver: Any | None = None,
    snapshot_restorer: Any | None = None,
    document_validator: Any | None = None,
) -> Mapping[str, Any]:
    """Restore one opaque baseline snapshot without closing the leased proxy."""

    selected_view = _lease_view(lease)
    session_uuid = selected_view["document_session_uuid"]
    if (
        not session_uuid
        or selected_view["source"] != "local"
        or not selected_view["is_v2"]
    ):
        raise RuntimeError("baseline restore is available only for a local v2 record")
    if selected_view["state"].upper() not in {
        "USER_INTERVENED",
        "UNLOCKED_DIRTY",
    }:
        raise RuntimeError("take over the selected document before restoring it")

    current = service.get({"document_session_uuid": session_uuid})
    if not isinstance(current, Mapping):
        raise RuntimeError("the selected recovery record is no longer active")
    current_view = _lease_view(current)
    if current_view["lease_id"] != selected_view["lease_id"]:
        raise RuntimeError("the selected recovery record changed before restore")
    if current_view["state"].upper() not in {
        "USER_INTERVENED",
        "UNLOCKED_DIRTY",
    }:
        raise RuntimeError("the selected recovery record no longer permits restore")
    snapshot_id = current_view["snapshot_id"]
    if not snapshot_id:
        raise RuntimeError("the selected lease has no recovery baseline snapshot")

    if gui_dispatcher is None:
        (
            gui_dispatcher,
            snapshot_path_resolver,
            snapshot_restorer,
            document_validator,
        ) = _runtime_restore_components()
    if not callable(snapshot_path_resolver) or not callable(snapshot_restorer):
        raise RuntimeError("lease baseline snapshot restore is unavailable")
    if not callable(document_validator):
        raise RuntimeError("snapshot post-restore validation is unavailable")
    if not callable(getattr(gui_dispatcher, "submit", None)):
        raise RuntimeError("the FreeCAD GUI dispatcher is not running")

    selector = {"document_session_uuid": session_uuid}

    def restore_gui() -> Mapping[str, Any]:
        latest = service.get(selector)
        if not isinstance(latest, Mapping):
            raise RuntimeError("the selected recovery record disappeared")
        latest_view = _lease_view(latest)
        if (
            latest_view["lease_id"] != current_view["lease_id"]
            or latest_view["snapshot_id"] != snapshot_id
            or latest_view["state"].upper() not in {"USER_INTERVENED", "UNLOCKED_DIRTY"}
        ):
            raise RuntimeError("the recovery lease changed while restore was queued")

        identity = _inspect_local_save_document_gui(
            service,
            document,
            session_uuid=session_uuid,
        )
        expected_document = latest.get("document", {})
        expected_document = (
            expected_document if isinstance(expected_document, Mapping) else {}
        )
        if str(getattr(identity, "name", "") or "") != str(
            expected_document.get("name") or ""
        ):
            raise RuntimeError("the live document name changed before restore")
        expected_comparison = str(expected_document.get("comparison_key") or "")
        if (
            expected_comparison
            and str(getattr(identity, "comparison_key", "") or "")
            != expected_comparison
        ):
            raise RuntimeError("the live document path changed before restore")

        restore_started = False
        try:
            snapshot_path = snapshot_path_resolver(snapshot_id)
            restore_started = True
            result = snapshot_restorer(
                document,
                snapshot_path,
                expected_document_name=str(getattr(identity, "name", "") or ""),
                expected_source_path=getattr(identity, "canonical_path", None),
                validator=document_validator,
            )
            if not isinstance(result, Mapping) or result.get("ok") is not True:
                raise RuntimeError(
                    "snapshot service did not confirm a complete restore"
                )
            observed = _inspect_local_save_document_gui(
                service,
                document,
                session_uuid=session_uuid,
            )
            if observed != identity:
                raise RuntimeError(
                    "restored live document no longer matches its lease identity"
                )
            if (
                result.get("dirty") is not True
                or require_document_modified(document) is not True
            ):
                raise RuntimeError("restored document was not marked dirty")
            updated = service.update_local_dirty(selector, dirty=True)
        except Exception:
            if restore_started:
                # A failed Document.load can have partially changed memory.
                # Keep the already-fenced recovery record conservatively dirty.
                try:
                    service.update_local_dirty(selector, dirty=True)
                except Exception:
                    pass
            raise

        public = _record_public_dict(updated)
        restored_view = _lease_view(public)
        if (
            restored_view["lease_id"] != current_view["lease_id"]
            or restored_view["document_session_uuid"] != session_uuid
        ):
            raise RuntimeError("restore did not preserve the selected lease identity")
        return {
            **dict(result),
            "restored_id": snapshot_id,
            "document_session_uuid": session_uuid,
            "lease_preserved": True,
            "lease": _redact_secrets(public),
        }

    submit = getattr(gui_dispatcher, "submit")
    return submit(
        restore_gui,
        timeout=_LOCAL_SAVE_GUI_TIMEOUT,
        request_id=f"local-restore-{uuid.uuid4()}",
    )


def _start_local_baseline_restore_async(
    lease: Mapping[str, Any],
    service: Any,
    document: Any,
    *,
    completion_emit: Callable[[Mapping[str, Any]], None],
    thread_factory: Callable[..., Any] = threading.Thread,
    **restore_dependencies: Any,
) -> Any:
    """Run restore orchestration off Qt and queue its result through a signal."""

    if not callable(completion_emit):
        raise TypeError("completion_emit must be callable")

    def run() -> None:
        try:
            result = _restore_local_baseline(
                lease,
                service,
                document,
                **restore_dependencies,
            )
        except Exception as exc:
            outcome: Mapping[str, Any] = {
                "ok": False,
                "error": str(exc),
                "error_type": type(exc).__name__,
            }
        else:
            outcome = {"ok": True, "result": result}
        try:
            completion_emit(outcome)
        except RuntimeError:
            pass

    worker = thread_factory(
        target=run,
        name="FreeCADMCP-local-baseline-restore",
        daemon=True,
    )
    worker.start()
    return worker


def _set_status_style(state: str | None) -> None:
    if _status_widget is None:
        return
    if not state:
        color = "#59636e"
    else:
        _icon, color, _label = _state_presentation(state)
    _status_widget.setStyleSheet(
        "QLabel#McpDocumentLockStatus {"
        f"color: {color}; font-weight: 600; padding: 1px 5px;"
        "}"
    )


def _refresh_lock_indicator_now() -> None:
    """Refresh widgets.  This private function must run on the Qt GUI thread."""

    global _status_widget, _dock_widget
    leases = _active_leases()
    _update_command_deterrence(leases)
    if _status_widget is None:
        return
    preferred = _select_preferred_lease(leases)
    if preferred is None:
        _status_widget.setText("No agent lock")
        _status_widget.setToolTip("No MCP document lease is active")
        _set_status_style(None)
        _status_widget.setVisible(True)
    else:
        view = _lease_view(preferred)
        text, tip = _lease_lines(preferred)
        icon, _color, _label = _state_presentation(view["state"])
        if len(leases) > 1:
            text += f" (+{len(leases) - 1} more)"
        _status_widget.setText(f"{icon} {text}")
        _status_widget.setToolTip(tip)
        _set_status_style(view["state"])
        _status_widget.setVisible(True)

    if _dock_widget is not None and hasattr(_dock_widget, "refresh_from_leases"):
        _dock_widget.refresh_from_leases(leases)


def refresh_lock_indicator() -> None:
    """Queue a refresh without touching a Qt widget in the calling thread."""

    # The callback is invoked by XML-RPC worker threads as well as GUI paths.
    # Always taking the signal route gives it one unambiguous threading rule.
    # The one-second GUI timer is the safe fallback during startup/shutdown.
    bridge = _refresh_bridge
    if bridge is not None:
        try:
            bridge.refresh_requested.emit()
        except RuntimeError:
            # Qt may already have destroyed the bridge during application exit.
            pass


def install_lock_indicator() -> None:
    """Create the permanent status widget and closable detail dock."""

    global _installed, _status_widget, _dock_widget, _refresh_timer, _refresh_bridge
    if _installed:
        return
    try:
        import FreeCADGui
        from PySide import QtCore, QtWidgets
    except ImportError:
        return

    try:
        main = FreeCADGui.getMainWindow()
    except Exception:
        return
    if main is None:
        return

    class _ClickableStatusLabel(QtWidgets.QLabel):
        clicked = QtCore.Signal()

        def mouseReleaseEvent(self, event):  # type: ignore[no-untyped-def]
            super().mouseReleaseEvent(event)
            self.clicked.emit()

    class _RefreshBridge(QtCore.QObject):
        refresh_requested = QtCore.Signal()
        local_save_completed = QtCore.Signal(object)
        local_restore_completed = QtCore.Signal(object)

        @QtCore.Slot()
        def refresh_now(self) -> None:
            _refresh_lock_indicator_now()

    status = _ClickableStatusLabel("No agent lock")
    status.setObjectName("McpDocumentLockStatus")
    status.setToolTip("No MCP document lease is active")
    try:
        main.statusBar().addPermanentWidget(status)
    except Exception:
        return
    _status_widget = status
    _set_status_style(None)

    bridge = _RefreshBridge(main)
    bridge.refresh_requested.connect(bridge.refresh_now, QtCore.Qt.QueuedConnection)
    _refresh_bridge = bridge

    dock = QtWidgets.QDockWidget("MCP Document Lock", main)
    dock.setObjectName("McpDocumentLockDock")
    dock.setFeatures(
        QtWidgets.QDockWidget.DockWidgetClosable
        | QtWidgets.QDockWidget.DockWidgetMovable
        | QtWidgets.QDockWidget.DockWidgetFloatable
    )
    # A close only hides the details.  It never releases a lease and never
    # removes the permanent status-bar widget.
    dock.setAttribute(QtCore.Qt.WA_DeleteOnClose, False)
    dock._mcp_local_save_in_progress = False  # type: ignore[attr-defined]
    dock._mcp_local_restore_in_progress = False  # type: ignore[attr-defined]

    container = QtWidgets.QWidget(dock)
    layout = QtWidgets.QVBoxLayout(container)
    selector_label = QtWidgets.QLabel("Document lease:", container)
    layout.addWidget(selector_label)
    selector = QtWidgets.QComboBox(container)
    selector.setObjectName("McpDocumentLockSelector")
    layout.addWidget(selector)

    info = QtWidgets.QPlainTextEdit(container)
    info.setReadOnly(True)
    info.setMaximumBlockCount(200)
    layout.addWidget(info)

    takeover_btn = QtWidgets.QPushButton(
        "Take over / fence agent for selected document…", container
    )
    save_clear_btn = QtWidgets.QPushButton(
        "Save, verify, and clear selected document…", container
    )
    restore_btn = QtWidgets.QPushButton(
        "Restore baseline for selected document…", container
    )
    keep_dirty_btn = QtWidgets.QPushButton(
        "Keep dirty and acknowledge selected document…", container
    )

    def _selected_lease() -> dict[str, Any] | None:
        record_id = selector.currentData()
        records = getattr(dock, "_mcp_leases_by_id", {})
        return records.get(str(record_id))

    def _local_recovery_busy() -> bool:
        return bool(
            getattr(dock, "_mcp_local_save_in_progress", False)
            or getattr(dock, "_mcp_local_restore_in_progress", False)
        )

    def _on_takeover() -> None:
        lease = _selected_lease()
        if lease is None:
            return
        view = _lease_view(lease)
        target = view["doc_key"] or view["document_session_uuid"]
        if not target:
            info.appendPlainText(
                "Takeover failed: selected record has no document identity"
            )
            return

        dirty_text = "has unsaved changes" if view["dirty"] else "is currently clean"
        baseline_text = (
            "a recovery baseline is available"
            if view["baseline_available"]
            else "no recovery baseline is available"
        )
        owner = _bounded_text(view["agent_id"] or view["client"])
        message = (
            f"Take over {view['filename']} from {owner or 'the current agent'}?\n\n"
            f"The document {dirty_text}, and {baseline_text}.\n"
            "This revokes the current agent credential and requires you to "
            "resolve the document by saving, restoring, or acknowledging dirty state."
        )
        answer = QtWidgets.QMessageBox.warning(
            dock,
            "Confirm document takeover",
            message,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel,
            QtWidgets.QMessageBox.Cancel,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return
        try:
            service = _v2_lease_service()
            session_uuid = view["document_session_uuid"]
            if service is not None and session_uuid and view["is_v2"]:
                document = _live_document_for_view(view, service)
                if document is None:
                    raise RuntimeError("the selected v2 document is no longer open")
                if view["source"] == "foreign_recovery":
                    result = _confirmed_foreign_takeover(
                        lease,
                        service,
                        document,
                        reason="Confirmed local GUI takeover of dead foreign owner",
                    )
                else:
                    try:
                        from document_lease.observer import take_over_selected_document
                    except ImportError:
                        from addon.FreeCADMCP.document_lease.observer import (
                            take_over_selected_document,
                        )

                    result = take_over_selected_document(
                        service_provider=lambda: service,
                        selected_document_provider=lambda: document,
                        reason="Confirmed local GUI takeover",
                    )
                if result is None:
                    raise RuntimeError("the selected v2 lease is no longer active")
            else:
                from document_lock import mark_user_intervened

                result = mark_user_intervened(str(target))
                if result is None:
                    raise RuntimeError("the selected lease is no longer active")
            refresh_lock_indicator()
        except Exception as exc:
            info.appendPlainText(f"Takeover failed: {_bounded_text(exc, limit=300)}")

    def _selected_v2_context() -> tuple[dict[str, Any], Any, Any]:
        lease = _selected_lease()
        if lease is None:
            raise RuntimeError("no document lease is selected")
        view = _lease_view(lease)
        service = _v2_lease_service()
        if service is None or not view["is_v2"] or view["source"] != "local":
            raise RuntimeError("the selected lease is not a local v2 recovery record")
        document = _live_document_for_view(view, service)
        if document is None:
            raise RuntimeError("the selected v2 document is no longer open")
        return lease, service, document

    def _on_keep_dirty() -> None:
        try:
            if _local_recovery_busy():
                raise RuntimeError("another local recovery action is still running")
            lease, service, document = _selected_v2_context()
            view = _lease_view(lease)
            if not _local_recovery_capabilities(lease, document)["keep_dirty"]:
                raise RuntimeError(
                    "take over the document and leave it dirty before acknowledging it"
                )
            answer = QtWidgets.QMessageBox.warning(
                dock,
                "Confirm dirty document acknowledgement",
                (
                    f"Keep {view['filename']} open with unsaved changes?\n\n"
                    "The agent credential is already revoked. A persistent "
                    "UNLOCKED_DIRTY recovery record will continue to block new "
                    "agent acquisitions until you save and clear it."
                ),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel,
                QtWidgets.QMessageBox.Cancel,
            )
            if answer != QtWidgets.QMessageBox.Yes:
                return
            _acknowledge_selected_dirty(lease, service, document)
            refresh_lock_indicator()
        except Exception as exc:
            info.appendPlainText(
                f"Keep-dirty acknowledgement failed: {_bounded_text(exc, limit=300)}"
            )

    def _on_save_and_clear() -> None:
        try:
            if _local_recovery_busy():
                raise RuntimeError(
                    "another local recovery action is already running for this dock"
                )
            lease, service, document = _selected_v2_context()
            view = _lease_view(lease)
            if not _local_recovery_capabilities(lease, document)["save_and_clear"]:
                raise RuntimeError(
                    "save-and-clear requires a taken-over saved document with a baseline"
                )
            answer = QtWidgets.QMessageBox.warning(
                dock,
                "Confirm verified local save",
                (
                    f"Save {view['filename']} to its current path, reopen-verify it "
                    "with the matching FreeCADCmd worker, and clear its lease?\n\n"
                    "The file is compared with the recorded baseline before FreeCAD "
                    "writes it. Any conflict, validation error, or sidecar failure "
                    "leaves the recovery record in place."
                ),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel,
                QtWidgets.QMessageBox.Cancel,
            )
            if answer != QtWidgets.QMessageBox.Yes:
                return
            (
                local_save_service,
                expectation_builder,
                worker_validator,
                snapshot_discarder,
                local_gui_dispatcher,
            ) = _runtime_save_components()
            dock._mcp_local_save_in_progress = True  # type: ignore[attr-defined]
            save_clear_btn.setEnabled(False)
            restore_btn.setEnabled(False)
            keep_dirty_btn.setEnabled(False)
            _start_verified_local_save_and_clear_async(
                lease,
                service,
                document,
                completion_emit=bridge.local_save_completed.emit,
                save_service=local_save_service,
                expectation_builder=expectation_builder,
                worker_validator=worker_validator,
                snapshot_discarder=snapshot_discarder,
                gui_dispatcher=local_gui_dispatcher,
            )
            info.appendPlainText(
                "Verified local save started; hashing and reopen validation "
                "are running in the background."
            )
        except Exception as exc:
            dock._mcp_local_save_in_progress = False  # type: ignore[attr-defined]
            info.appendPlainText(
                f"Verified save-and-clear failed: {_bounded_text(exc, limit=300)}"
            )
            refresh_lock_indicator()

    @QtCore.Slot(object)
    def _on_local_save_completed(outcome: Any) -> None:
        """Handle the worker outcome only after Qt queues it onto this thread."""

        dock._mcp_local_save_in_progress = False  # type: ignore[attr-defined]
        payload = outcome if isinstance(outcome, Mapping) else {}
        if payload.get("ok"):
            result = payload.get("result", {})
            result = result if isinstance(result, Mapping) else {}
            saved = result.get("save", {})
            saved = saved if isinstance(saved, Mapping) else {}
            info.appendPlainText(
                "Verified local save completed and the document lease was cleared: "
                + _bounded_text(saved.get("path", "selected document"), limit=260)
            )
        else:
            info.appendPlainText(
                "Verified save-and-clear failed: "
                + _bounded_text(payload.get("error", "unknown error"), limit=300)
            )
        refresh_lock_indicator()

    def _on_restore_baseline() -> None:
        try:
            if _local_recovery_busy():
                raise RuntimeError(
                    "another local recovery action is already running for this dock"
                )
            lease, service, document = _selected_v2_context()
            view = _lease_view(lease)
            if not _local_recovery_capabilities(lease, document)["restore_baseline"]:
                raise RuntimeError(
                    "restore requires a taken-over document with a lease snapshot"
                )
            modified_state = document_modified_state(document)
            if modified_state is True:
                dirty_text = "currently has unsaved changes"
            elif modified_state is False:
                dirty_text = "is currently clean"
            else:
                dirty_text = "has an unknown modified state"
            answer = QtWidgets.QMessageBox.warning(
                dock,
                "Confirm baseline restore",
                (
                    f"Replace the in-memory contents of {view['filename']} with "
                    f"its lease baseline?\n\nThe document {dirty_text}. This action "
                    "does not overwrite the source FCStd or close/reopen the document. "
                    "The same session UUID and recovery lease remain active, and the "
                    "restored document stays dirty until a verified save-and-clear."
                ),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel,
                QtWidgets.QMessageBox.Cancel,
            )
            if answer != QtWidgets.QMessageBox.Yes:
                return
            (
                restore_dispatcher,
                snapshot_path_resolver,
                snapshot_restorer,
                document_validator,
            ) = _runtime_restore_components()
            dock._mcp_local_restore_in_progress = True  # type: ignore[attr-defined]
            save_clear_btn.setEnabled(False)
            restore_btn.setEnabled(False)
            keep_dirty_btn.setEnabled(False)
            _start_local_baseline_restore_async(
                lease,
                service,
                document,
                completion_emit=bridge.local_restore_completed.emit,
                gui_dispatcher=restore_dispatcher,
                snapshot_path_resolver=snapshot_path_resolver,
                snapshot_restorer=snapshot_restorer,
                document_validator=document_validator,
            )
            info.appendPlainText(
                "Lease baseline restore started; the source file remains untouched."
            )
        except Exception as exc:
            dock._mcp_local_restore_in_progress = False  # type: ignore[attr-defined]
            info.appendPlainText(
                f"Baseline restore failed: {_bounded_text(exc, limit=300)}"
            )
            refresh_lock_indicator()

    @QtCore.Slot(object)
    def _on_local_restore_completed(outcome: Any) -> None:
        dock._mcp_local_restore_in_progress = False  # type: ignore[attr-defined]
        payload = outcome if isinstance(outcome, Mapping) else {}
        if payload.get("ok"):
            result = payload.get("result", {})
            result = result if isinstance(result, Mapping) else {}
            info.appendPlainText(
                "Lease baseline restored in place; session and lease preserved: "
                + _bounded_text(
                    result.get("document_session_uuid", "selected document"),
                    limit=100,
                )
            )
        else:
            info.appendPlainText(
                "Baseline restore failed: "
                + _bounded_text(payload.get("error", "unknown error"), limit=300)
            )
        refresh_lock_indicator()

    takeover_btn.clicked.connect(_on_takeover)
    layout.addWidget(takeover_btn)
    save_clear_btn.clicked.connect(_on_save_and_clear)
    layout.addWidget(save_clear_btn)
    restore_btn.clicked.connect(_on_restore_baseline)
    layout.addWidget(restore_btn)
    keep_dirty_btn.clicked.connect(_on_keep_dirty)
    layout.addWidget(keep_dirty_btn)
    dock.setWidget(container)
    _connect_queued_qt_signal(
        bridge.local_save_completed,
        _on_local_save_completed,
        QtCore,
    )
    _connect_queued_qt_signal(
        bridge.local_restore_completed,
        _on_local_restore_completed,
        QtCore,
    )

    def refresh_from_leases(leases: list[dict[str, Any]]) -> None:
        leases = [_redact_secrets(item) for item in leases]
        previous_id = str(selector.currentData() or "")
        preferred = _select_preferred_lease(leases)
        preferred_id = _lease_view(preferred)["record_id"] if preferred else ""

        records: dict[str, dict[str, Any]] = {}
        selector.blockSignals(True)
        selector.clear()
        for lease in leases:
            view = _lease_view(lease)
            record_id = view["record_id"]
            records[record_id] = lease
            selector.addItem(
                f"{view['filename']} — {view['state']}",
                record_id,
            )
        dock._mcp_leases_by_id = records  # type: ignore[attr-defined]

        desired_id = previous_id if previous_id in records else preferred_id
        if desired_id:
            index = selector.findData(desired_id)
            if index >= 0:
                selector.setCurrentIndex(index)
        selector.blockSignals(False)
        selector.setEnabled(bool(leases))

        if not leases:
            takeover_btn.setEnabled(False)
            save_clear_btn.setEnabled(False)
            restore_btn.setEnabled(False)
            keep_dirty_btn.setEnabled(False)
            info.setPlainText("No active MCP document leases.")
            return
        selected = _selected_lease() or preferred or leases[0]
        selected_view = _lease_view(selected)
        selected_service = _v2_lease_service()
        selected_document = (
            _live_document_for_view(selected_view, selected_service)
            if selected_service is not None and selected_view["is_v2"]
            else None
        )
        capabilities = _local_recovery_capabilities(selected, selected_document)
        local_recovery_busy = _local_recovery_busy()
        takeover_btn.setEnabled(capabilities["takeover"])
        save_clear_btn.setEnabled(
            capabilities["save_and_clear"] and not local_recovery_busy
        )
        restore_btn.setEnabled(
            capabilities["restore_baseline"] and not local_recovery_busy
        )
        keep_dirty_btn.setEnabled(
            capabilities["keep_dirty"] and not local_recovery_busy
        )
        takeover_btn.setToolTip(
            "Revokes the selected local or proven-dead imported owner and increments its fencing generation."
            if capabilities["takeover"]
            else "Takeover requires live selected-document identity and locally provable owner death."
        )
        save_clear_btn.setToolTip(
            "Same-path save with hash, archive, matching-worker validation, and CAS release."
            if capabilities["save_and_clear"]
            else "Requires a local taken-over v2 document with a saved baseline."
        )
        restore_btn.setToolTip(
            "Loads the owner-only lease snapshot in place and preserves the session/lease."
            if capabilities["restore_baseline"]
            else "Requires a local taken-over v2 document with a lease snapshot."
        )
        keep_dirty_btn.setToolTip(
            "Persists UNLOCKED_DIRTY; new agent acquisitions remain blocked."
            if capabilities["keep_dirty"]
            else "Requires a local taken-over document that FreeCAD reports as dirty."
        )
        _text, tip = _lease_lines(selected)
        info.setPlainText(tip)

    def _refresh_selected_detail(_index: int) -> None:
        selected = _selected_lease()
        if selected is not None:
            _text, tip = _lease_lines(selected)
            info.setPlainText(tip)
            view = _lease_view(selected)
            service = _v2_lease_service()
            document = (
                _live_document_for_view(view, service)
                if service is not None and view["is_v2"]
                else None
            )
            capabilities = _local_recovery_capabilities(selected, document)
            local_recovery_busy = _local_recovery_busy()
            takeover_btn.setEnabled(capabilities["takeover"])
            save_clear_btn.setEnabled(
                capabilities["save_and_clear"] and not local_recovery_busy
            )
            restore_btn.setEnabled(
                capabilities["restore_baseline"] and not local_recovery_busy
            )
            keep_dirty_btn.setEnabled(
                capabilities["keep_dirty"] and not local_recovery_busy
            )

    selector.currentIndexChanged.connect(_refresh_selected_detail)
    dock.refresh_from_leases = refresh_from_leases  # type: ignore[attr-defined]

    try:
        main.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock)
        _dock_widget = dock
    except Exception:
        _dock_widget = None

    def _show_details() -> None:
        if _dock_widget is not None:
            _dock_widget.show()
            _dock_widget.raise_()

    status.clicked.connect(_show_details)

    timer = QtCore.QTimer(main)
    timer.setInterval(1000)
    timer.timeout.connect(_refresh_lock_indicator_now)
    timer.start()
    _refresh_timer = timer

    try:
        from document_lock import set_gui_update_callback

        # document_lock invokes this from both XML-RPC and GUI paths.  The
        # public entry point performs the required queued signal hand-off.
        set_gui_update_callback(refresh_lock_indicator)
    except Exception:
        pass

    _installed = True
    _refresh_lock_indicator_now()
