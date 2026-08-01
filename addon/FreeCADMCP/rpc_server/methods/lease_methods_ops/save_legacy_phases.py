"""Legacy save GUI phase implementations."""

import hmac

from ...save_service import DomainValidationError, SaveServiceError
from ._common import _rpc_mod, document_modified_or_dirty


def legacy_save_failure_response(
    self, exc, *, phase, dl, token, request_id, captured_identity, inflight, dirty=None
):
    if phase.get("doc_key") and phase.get("save_state_entered"):
        try:
            document = _rpc_mod().FreeCAD.getDocument(phase.get("document_name", ""))
            observed_dirty = (
                document_modified_or_dirty(document)
                if document is not None
                else True
            )
            dl.transition_lease(
                phase["doc_key"],
                token,
                dl.LeaseState.LOCKED_ERROR.value,
                current_operation="save_failed",
                document_dirty=(observed_dirty if dirty is None else bool(dirty)),
                request_id=request_id or None,
                error={
                    "code": str(getattr(exc, "code", type(exc).__name__.upper())),
                    "message": _rpc_mod()._redact_rpc_diagnostic(
                        exc,
                        identity=captured_identity,
                        inflight=inflight,
                    ),
                },
            )
        except Exception:
            pass
    if isinstance(exc, SaveServiceError):
        return {
            "success": False,
            "error_code": exc.code,
            "error": str(exc),
            "save_error": exc.to_dict(request_id=request_id or None),
        }
    return {
        "success": False,
        "error_code": str(getattr(exc, "code", type(exc).__name__.upper())),
        "error": _rpc_mod()._redact_rpc_diagnostic(
            exc, identity=captured_identity, inflight=inflight
        ),
    }


def legacy_prepare_gui(
    self,
    *,
    selector,
    captured_identity,
    request_id,
    phase,
    dl,
    validation_profile,
    token,
    inflight,
):
    document, document_identity = _rpc_mod()._live_document_from_selector(selector)
    source_path = str(getattr(document, "FileName", "") or "")
    if not source_path:
        raise ValueError("Protocol-v1 compatibility supports same-path save only")
    doc_key = dl.resolve_doc_key(
        doc_name=document_identity.name,
        file_path=source_path,
    )
    authorized = dl.check_persisted_mutation_allowed(
        doc_key,
        identity=captured_identity,
        allowed_states={
            dl.LeaseState.LOCKED_IDLE.value,
            dl.LeaseState.LOCKED_ERROR.value,
        },
    )
    if not authorized.get("success"):
        return authorized
    record = dl.get_lease(doc_key)
    if record is None or not record.baseline_hash:
        raise RuntimeError("The compatibility lease has no accepted file baseline")
    reference_preflight = _rpc_mod().inspect_references_gui(
        document_identity.name,
        only_invalid=True,
        validate=True,
    )
    if not reference_preflight.get("ok"):
        raise DomainValidationError(
            "Unable to inspect live document references before save",
            stage="live_reference_preflight",
            path=source_path,
            mutation_may_have_occurred=False,
            details={"inspection": reference_preflight},
        )
    invalid_references = list(reference_preflight.get("references") or ())
    if invalid_references:
        raise DomainValidationError(
            (
                f"Typed save blocked by {len(invalid_references)} "
                "invalid live reference properties"
            ),
            stage="live_reference_preflight",
            path=source_path,
            mutation_may_have_occurred=False,
            details={
                "invalid_count": len(invalid_references),
                "references": invalid_references[:100],
            },
        )
    phase.update(
        doc_key=doc_key,
        document_name=document_identity.name,
        source_path=source_path,
        expected_sha256=record.baseline_hash,
        validation_expectations=_rpc_mod()._saved_document_expectations(document),
    )
    transitioned = dl.transition_lease(
        doc_key,
        token,
        dl.LeaseState.LOCKED_SAVING.value,
        current_operation="saving",
        request_id=request_id or None,
    )
    if not transitioned.get("success"):
        return transitioned
    phase["save_state_entered"] = True
    return {"success": True}


def legacy_invoke_gui(
    self,
    *,
    phase,
    dl,
    captured_identity,
    request_id,
    preflight,
    inflight,
):
    marker_keys = [
        phase["doc_key"],
        phase["document_name"],
        phase["source_path"],
    ]
    attribution_started = False
    try:
        document = _rpc_mod().FreeCAD.getDocument(phase["document_name"])
        if document is None:
            raise RuntimeError("document closed before save invocation")
        authorized = dl.check_persisted_mutation_allowed(
            phase["doc_key"],
            identity=captured_identity,
            allowed_states={dl.LeaseState.LOCKED_SAVING.value},
        )
        if not authorized.get("success"):
            raise RuntimeError(
                authorized.get("error") or "Compatibility lease authorization failed"
            )
        dl.begin_agent_mutation_scope(request_id, marker_keys)
        attribution_started = True
        phase["invocation"] = _rpc_mod().save_service.invoke_save_gui(document, preflight)
        return {"success": True}
    finally:
        if attribution_started:
            dl.end_agent_mutation_scope(request_id, marker_keys)


def legacy_promote_gui(self, *, phase, dl, token, result):
    document = _rpc_mod().FreeCAD.getDocument(phase["document_name"])
    if document is None:
        raise RuntimeError("saved document closed before lease promotion")
    _rpc_mod().save_service.revalidate_saved_document_gui(document, result)
    promoted = dl.mark_save_verified(
        phase["doc_key"],
        token,
        baseline_mtime=result.baseline.mtime_ns / 1_000_000_000,
        baseline_hash=result.baseline.sha256,
    )
    if not promoted.get("success"):
        return promoted
    return {
        "success": True,
        "save": result.to_dict(),
        "lease": promoted["lease"],
        "aliases": {
            "document_session_uuid": promoted["lease"].get(
                "document_session_uuid", ""
            ),
            "canonical_path": result.path,
            "previous_path": result.previous_path,
        },
        "compatibility_protocol": 1,
    }


def hash_legacy_baseline(self, phase, validation_profile):
    lease = _rpc_mod()._import_document_lease()
    baseline = lease.capture_file_baseline(
        phase["source_path"],
        platform=(
            _rpc_mod().document_identity_service.platform
            if _rpc_mod().document_identity_service is not None
            else None
        ),
    )
    if not hmac.compare_digest(str(baseline.sha256), str(phase["expected_sha256"])):
        raise RuntimeError(
            "The saved file changed after the compatibility lease was acquired"
        )
    return _rpc_mod().save_service.prepare_save(
        phase["source_path"],
        expected_baseline=baseline,
        expected_path=phase["source_path"],
        validation_profile=validation_profile,
    )
