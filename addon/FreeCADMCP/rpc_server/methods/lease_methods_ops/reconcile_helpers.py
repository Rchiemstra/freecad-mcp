"""Stale lease reconciliation helpers."""
try: from ....dispatch.request_cancellation_error import RequestCancellationError  # noqa: E701, I001 - frozen census lines
except ImportError: from dispatch.request_cancellation_error import RequestCancellationError  # noqa: E701, I001 - frozen census lines
from ._common import _rpc_mod, require_document_modified


def prepare_reconcile_gui(
    self,
    *,
    credential,
    inflight,
    captured_identity,
    phase,
    lease,
):
    if inflight is not None:
        inflight.token.checkpoint("lease_reconcile_prepare_gui")
    parsed = _rpc_mod()._credential_from_wire(credential, captured_identity)
    already = _rpc_mod()._stale_reconcile_already_recovered(parsed)
    if already is not None:
        return {
            "success": True,
            "idempotent": True,
            "lease": already.to_public_dict(),
        }
    document, identity = _rpc_mod()._live_document_from_selector(
        {"document_session_uuid": parsed.document_session_uuid}
    )
    record = _rpc_mod().document_lease_service.authorize(
        parsed,
        selector={"document_session_uuid": parsed.document_session_uuid},
        allowed_states={lease.LeaseState.STALE},
    )
    live_identity = _rpc_mod().document_identity_service.inspect_registered_document(
        parsed.document_session_uuid, document
    )
    if identity != record.document or live_identity != record.document:
        raise lease.LiveDocumentValidationError(
            "live document identity does not match the stale lease"
        )
    if record.user_intervened:
        raise lease.LiveDocumentValidationError(
            "stale reconciliation refused after user intervention"
        )
    reconcile_kind = _rpc_mod()._stale_reconcile_classify(record)
    phase.update(
        credential=parsed,
        document=document,
        identity=live_identity,
        record=record,
        reconcile_kind=reconcile_kind,
    )
    if reconcile_kind == "saved":
        phase["baseline"] = record.baseline
        phase["canonical_path"] = record.document.canonical_path
    return {"success": True}


def capture_reconcile_baseline(self, phase, lease, captured_identity):
    try:
        self._request_checkpoint("lease_reconcile_hash")
        fresh_baseline = lease.capture_file_baseline(
            phase["canonical_path"],
            platform=_rpc_mod().document_identity_service.platform,
        )
        self._request_checkpoint("lease_reconcile_hash_complete")
        return fresh_baseline
    except RequestCancellationError:
        raise
    except Exception as exc:
        return _rpc_mod()._lease_service_error(
            lease.LiveDocumentValidationError(
                f"unable to capture a stable reconciliation baseline: {exc}"
            ),
            request_id=captured_identity.get("request_id"),
        )


def commit_reconcile_gui(
    self,
    *,
    inflight,
    captured_identity,
    phase,
    lease,
    fresh_baseline,
):
    if inflight is not None:
        inflight.token.checkpoint("lease_reconcile_commit_gui")
    parsed = phase["credential"]
    document, identity = _rpc_mod()._live_document_from_selector(
        {"document_session_uuid": parsed.document_session_uuid}
    )
    if document is not phase["document"]:
        raise lease.LiveDocumentValidationError(
            "live document proxy changed during stale reconciliation"
        )
    record = _rpc_mod().document_lease_service.authorize(
        parsed,
        selector={"document_session_uuid": parsed.document_session_uuid},
        allowed_states={lease.LeaseState.STALE},
    )
    if record != phase["record"]:
        raise lease.CoordinationError(
            "stale lease authority changed during baseline capture"
        )
    live_identity = _rpc_mod().document_identity_service.inspect_registered_document(
        parsed.document_session_uuid, document
    )
    if (
        identity != phase["identity"]
        or live_identity != phase["identity"]
        or live_identity != record.document
    ):
        raise lease.LiveDocumentValidationError(
            "live document identity changed during baseline capture"
        )
    evidence = build_reconcile_evidence(
        phase, document, live_identity, record, lease, fresh_baseline
    )
    self._touch_inflight_credential(parsed, inflight)
    if inflight is not None:
        inflight.token.begin_irreversible("lease_reconcile_state_commit")
    return {
        "success": True,
        "lease": _rpc_mod().document_lease_service.reconcile_stale(
            parsed, validation=evidence
        ).to_public_dict(),
    }


def build_reconcile_evidence(phase, document, live_identity, record, lease, fresh_baseline):
    reconcile_kind = phase["reconcile_kind"]
    if reconcile_kind == "saved":
        _rpc_mod()._assert_mutation_file_metadata_unchanged(record)
        baseline_matches = bool(
            fresh_baseline == phase["baseline"]
            and fresh_baseline == record.baseline
        )
        if not baseline_matches:
            raise lease.LiveDocumentValidationError(
                "fresh reconciliation baseline does not exactly match "
                "the persisted accepted baseline"
            )
        return lease.LiveDocumentValidation(
            document=live_identity,
            document_modified=require_document_modified(document),
            baseline=fresh_baseline,
            baseline_validated=True,
        )
    if reconcile_kind == "never_saved":
        _rpc_mod()._assert_never_saved_stale_continuity(
            record, document, phase["credential"], live_identity
        )
        return lease.LiveDocumentValidation(
            document=live_identity,
            document_modified=require_document_modified(document),
            baseline=None,
            baseline_validated=True,
        )
    raise lease.LiveDocumentValidationError(
        f"unsupported stale reconcile kind: {reconcile_kind!r}"
    )
