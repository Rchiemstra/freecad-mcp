"""Stale lease reconciliation helpers."""

import logging
from typing import Any

try:
    from document_state import require_document_modified
except ImportError:
    from addon.FreeCADMCP.document_state import require_document_modified

from ..lease_runtime import _import_document_lease
from ..snapshot_service import discard_lease_baseline_snapshot, recovery_snapshot_path

logger = logging.getLogger("FreeCADMCP.rpc_server")


def _recovery_snapshot_intact(snapshot_id: str | None) -> bool:
    if not snapshot_id:
        return False
    try:
        path = recovery_snapshot_path(snapshot_id)
    except Exception:
        return False
    return path.is_file()


def _stale_reconcile_saved_baseline_ready(record) -> bool:
    """Return whether *record* has an on-disk baseline for stale reconcile."""

    return bool(record.document.canonical_path and record.baseline is not None)


def _stale_reconcile_never_saved_ready(record) -> bool:
    """Return whether *record* is a never-saved lease eligible for D5 reconcile."""

    return bool(
        not record.document.canonical_path
        and record.baseline is None
        and not record.validation_complete
    )


def _stale_reconcile_classify(record):
    """Classify stale reconcile evidence as saved-baseline or never-saved D5."""

    lease = _import_document_lease()
    if _stale_reconcile_saved_baseline_ready(record):
        return "saved"
    if _stale_reconcile_never_saved_ready(record):
        return "never_saved"
    if record.document.canonical_path and record.baseline is None:
        raise lease.LiveDocumentValidationError(
            "stale reconciliation requires a saved verified baseline"
        )
    raise lease.LiveDocumentValidationError(
        "stale reconciliation evidence is incomplete or inconsistent"
    )


def _assert_never_saved_stale_continuity(
    record,
    document,
    parsed,
    live_identity,
    *,
    document_identity_service,
):
    """Prove in-memory continuity for a never-saved dirty stale lease (D5)."""

    lease = _import_document_lease()
    if not _stale_reconcile_never_saved_ready(record):
        raise lease.LiveDocumentValidationError(
            "stale reconciliation record is not a never-saved lease"
        )
    if record.user_intervened:
        raise lease.LiveDocumentValidationError(
            "stale reconciliation refused after user intervention"
        )
    if record.dirty is not True:
        raise lease.LiveDocumentValidationError(
            "never-saved stale reconciliation requires a dirty lease record"
        )
    if record.last_mutation_revision < 1:
        raise lease.LiveDocumentValidationError(
            "never-saved stale reconciliation has no recorded mutation"
        )
    document_modified = require_document_modified(document)
    if document_modified != record.dirty:
        raise lease.LiveDocumentValidationError(
            "live GUI document modified state no longer matches the stale record"
        )
    if live_identity.name != record.document.name:
        raise lease.LiveDocumentValidationError(
            "live document name changed during stale reconciliation"
        )
    if not _recovery_snapshot_intact(record.snapshot_id):
        raise lease.LiveDocumentValidationError(
            "never-saved stale reconciliation requires an intact recovery snapshot"
        )
    bound_session = document_identity_service.registered_session_uuid(document)
    if bound_session != parsed.document_session_uuid:
        raise lease.LiveDocumentValidationError(
            "live document proxy is not registered to this lease session"
        )


def _stale_reconcile_already_recovered(parsed, *, document_lease_service):
    """Return the lease record when reconcile already succeeded for *parsed*."""

    lease = _import_document_lease()
    try:
        return document_lease_service.authorize(
            parsed,
            selector={"document_session_uuid": parsed.document_session_uuid},
            allowed_states={lease.LeaseState.LOCKED_IDLE},
        )
    except Exception:
        return None


def _discard_terminal_snapshot(terminal, *, logger_override=None):
    snapshot_id = (
        terminal.get("document_state", {}).get("snapshot_id")
        if isinstance(terminal, dict)
        else None
    )
    if snapshot_id:
        try:
            discard_lease_baseline_snapshot(snapshot_id)
        except Exception:
            (logger_override or logger).warning(
                "Released lease but could not remove recovery snapshot %s",
                snapshot_id,
                exc_info=True,
            )


def _v2_status_for_context(context, *, document_lease_service):
    if document_lease_service is None:
        return []
    document_ids = {
        item.get("document_session_uuid")
        for item in context.get("identity", {}).get("lease_credentials", [])
        if isinstance(item, dict)
    }
    return [
        record
        for record in document_lease_service.list_records()
        if record.get("document", {}).get("session_uuid") in document_ids
    ]


def _snapshot_mutation_context_for_request(
    *, document_lease_service, import_document_lock
) -> dict[str, Any]:
    """Return core generations and observer attribution for a snapshot caller."""

    if document_lease_service is None:
        return {
            "generations": None,
            "request_id": "",
            "document_keys": (),
        }
    try:
        identity = import_document_lock().get_request_identity()
    except Exception:
        return {
            "generations": {},
            "request_id": "",
            "document_keys": (),
        }
    runtime_id = str(identity.get("instance_id") or "")
    if not runtime_id:
        return {
            "generations": {},
            "request_id": "",
            "document_keys": (),
        }
    generations: dict[str, int] = {}
    document_keys: set[str] = set()
    for record in document_lease_service.list_records():
        owner = record.get("owner") or {}
        document = record.get("document") or {}
        if str(owner.get("mcp_instance_id") or "") != runtime_id:
            continue
        name = str(document.get("name") or "")
        generation = int(record.get("generation") or 0)
        if name and generation > 0:
            generations[name] = generation
            document_keys.update(
                str(value)
                for value in (
                    name,
                    document.get("session_uuid"),
                    document.get("canonical_path"),
                    document.get("comparison_key"),
                )
                if value
            )
    return {
        "generations": generations,
        "request_id": str(identity.get("request_id") or ""),
        "document_keys": tuple(sorted(document_keys)),
    }
