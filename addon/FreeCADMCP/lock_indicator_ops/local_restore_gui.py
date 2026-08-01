from __future__ import annotations

import contextlib
from collections.abc import Mapping
from typing import Any

try:
    from document_state import require_document_modified
except ImportError:
    from addon.FreeCADMCP.document_state import require_document_modified

from .lease_view import _lease_view
from .local_save import _inspect_local_save_document_gui
from .secret_redaction import _redact_secrets


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
    selector = {"document_session_uuid": session_uuid}
    identity, _latest = _validate_restore_identity(
        service=service,
        document=document,
        session_uuid=session_uuid,
        current_view=current_view,
        snapshot_id=snapshot_id,
    )
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
            raise RuntimeError("snapshot service did not confirm a complete restore")
        observed = _inspect_local_save_document_gui(
            service,
            document,
            session_uuid=session_uuid,
        )
        if observed != identity:
            raise RuntimeError(
                "restored live document no longer matches its lease identity"
            )
        if result.get("dirty") is not True or require_document_modified(document) is not True:
            raise RuntimeError("restored document was not marked dirty")
        updated = service.update_local_dirty(selector, dirty=True)
    except Exception:
        if restore_started:
            with contextlib.suppress(Exception):
                service.update_local_dirty(selector, dirty=True)
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
