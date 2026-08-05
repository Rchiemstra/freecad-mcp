from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .lease_view import _lease_view
from .local_save import _inspect_local_save_document_gui

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


def _record_public_dict(record: Any) -> Mapping[str, Any]:
    if isinstance(record, Mapping):
        return record
    render = getattr(record, "to_public_dict", None)
    if callable(render):
        value = render()
        if isinstance(value, Mapping):
            return value
    raise RuntimeError("lease service returned an invalid recovery record")


def _validate_restore_identity(
    *,
    service: Any,
    document: Any,
    session_uuid: str,
    current_view: Mapping[str, Any],
    snapshot_id: str,
) -> Any:
    latest = service.get({"document_session_uuid": session_uuid})
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
        and str(getattr(identity, "comparison_key", "") or "") != expected_comparison
    ):
        raise RuntimeError("the live document path changed before restore")
    return identity, latest


def _run_restore_gui_phase(
    *,
    service: Any,
    document: Any,
    session_uuid: str,
    current_view: Mapping[str, Any],
    snapshot_id: str,
    snapshot_path_resolver: Any,
    snapshot_restorer: Any,
    document_validator: Any,
) -> Mapping[str, Any]:
    """Return the frozen result for retired in-GUI baseline restore authority."""

    del (
        service,
        document,
        session_uuid,
        current_view,
        snapshot_id,
        snapshot_path_resolver,
        snapshot_restorer,
        document_validator,
    )
    return _legacy_lease_authority_removed()
