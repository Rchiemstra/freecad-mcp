from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

try:
    from document_state import document_modified_state, require_document_modified
except ImportError:
    from addon.FreeCADMCP.document_state import (
        document_modified_state,
        require_document_modified,
    )

from .constants import _AGENT_OWNED_STATES
from .lease_view import _is_eligible_exact_owner_stale_timeout, _lease_view
from .runtime_bindings import current_runtime_bindings


def _v2_lease_service() -> Any | None:
    """Return the service explicitly exposed by the add-on composition root."""

    bindings = current_runtime_bindings()
    return bindings.current_lease_service() if bindings is not None else None


def _live_document_for_view(view: Mapping[str, Any], service: Any) -> Any | None:
    """Resolve the exact live document selected in the dock."""

    bindings = current_runtime_bindings()
    freecad = bindings.freecad if bindings is not None else None
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
    eligible_auto_stale = _is_eligible_exact_owner_stale_timeout(view)
    return {
        "takeover": bool(
            not eligible_auto_stale
            and (local or imported_foreign)
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


def _connect_queued_qt_signal(
    signal: Any, slot: Callable[..., Any], qt_core: Any
) -> None:
    """Connect a cross-thread completion signal with an explicit Qt queue."""

    try:
        queued = qt_core.Qt.ConnectionType.QueuedConnection
    except AttributeError:
        queued = qt_core.Qt.QueuedConnection
    signal.connect(slot, queued)
