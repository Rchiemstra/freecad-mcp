from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from .constants import _AGENT_OWNED_STATES
from .lease_view import _is_eligible_exact_owner_stale_timeout, _lease_view
from .runtime_bindings import current_runtime_bindings

_LEGACY_MESSAGE = (
    "Document authority is owned by native FreeCAD collaboration."
)


def _legacy_lease_authority_removed() -> dict[str, object]:
    return {
        "success": False,
        "ok": False,
        "error_code": "LEGACY_LEASE_AUTHORITY_REMOVED",
        "error": _LEGACY_MESSAGE,
    }


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
            and document is not None
            and getattr(document, "Modified", None) is True
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
    """Return the frozen result for retired foreign takeover authority."""

    del lease, service, document, reason
    return _legacy_lease_authority_removed()


def _acknowledge_selected_dirty(
    lease: Mapping[str, Any], service: Any, document: Any
) -> Mapping[str, Any]:
    """Return the frozen result for retired keep-dirty authority."""

    del lease, service, document
    return _legacy_lease_authority_removed()


def _connect_queued_qt_signal(
    signal: Any, slot: Callable[..., Any], qt_core: Any
) -> None:
    """Connect a cross-thread completion signal with an explicit Qt queue."""

    try:
        queued = qt_core.Qt.ConnectionType.QueuedConnection
    except AttributeError:
        queued = qt_core.Qt.QueuedConnection
    signal.connect(slot, queued)
