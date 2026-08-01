"""Promotion-phase helpers for typed save."""

from ...mutation_guard import (
    RollbackCoverage,
    ValidationProfile,
    calculate_document_health_delta,
    capture_document_health,
)
from ._common import _rpc_mod, require_document_modified


def revalidate_save_promotion(credential, phase, lease):
    record = _rpc_mod().document_lease_service.authorize(
        credential,
        selector={"document_session_uuid": phase["document_session_uuid"]},
        allowed_states={lease.LeaseState.LOCKED_SAVING},
    )
    if (
        record.state_revision != phase["saving_state_revision"]
        or record.last_mutation_revision != phase["saving_mutation_revision"]
    ):
        raise lease.CoordinationError(
            "lease changed while the saved file was being validated"
        )
    return record


def assert_saved_path_matches(document, phase, result, lease):
    live_identity = _rpc_mod().document_identity_service.inspect_registered_document(
        phase["document_session_uuid"], document
    )
    _canonical, saved_comparison = lease.canonicalize_path(
        result.path, platform=_rpc_mod().document_identity_service.platform
    )
    if live_identity.comparison_key != saved_comparison:
        raise lease.CoordinationError(
            "live document path changed before save promotion"
        )
    return live_identity


def build_save_promotion_response(
    self,
    *,
    credential,
    result,
    phase,
    mode,
    validation_profile,
):
    response = {
        "success": True,
        "save": result.to_dict(),
        "lease": None,
        "aliases": {
            "document_session_uuid": (credential.document_session_uuid),
            "canonical_path": result.path,
            "previous_path": result.previous_path,
        },
    }
    health_after = capture_document_health(
        _rpc_mod().FreeCAD.getDocument(phase["document_name"]),
        profile=ValidationProfile(str(validation_profile).lower()),
    )
    health_delta = calculate_document_health_delta(
        phase["health_before"],
        health_after,
    )
    response["document_health"] = self._aggregate_document_health([health_delta])
    response["document_health"]["save_reopen_validation"] = result.to_dict()
    evidence = self._unknown_mutation_evidence(
        f"{mode}_document",
        declared_documents=(phase["document_name"],),
        coverage=RollbackCoverage.PARTIAL,
    )
    response["transaction"] = evidence["transaction"]
    response["mutation_scope"] = evidence["mutation_scope"]
    return response


def maybe_release_after_save(
    self,
    *,
    credential,
    document,
    result,
    inflight,
    response,
):
    promoted_identity = _rpc_mod().document_identity_service.inspect_registered_document(
        credential.document_session_uuid, document
    )
    lease = _rpc_mod()._import_document_lease()
    evidence = lease.LiveDocumentValidation(
        document=promoted_identity,
        document_modified=require_document_modified(document),
        baseline=result.baseline,
        baseline_validated=True,
    )
    if inflight is not None:
        inflight.token.begin_irreversible("finalize_release_sidecar_cas")
    response["release"] = _rpc_mod().document_lease_service.release_clean(
        credential, validation=evidence
    )
    try:
        _rpc_mod()._import_core_authority().sync_clear_from_release(document)
    except Exception:
        _rpc_mod().FreeCAD.Console.PrintWarning(
            "[MCP] core mutation owner clear failed after finalize\n"
        )
    _rpc_mod()._discard_terminal_snapshot(response["release"])
    response["released"] = True
    return response
