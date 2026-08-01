"""Prepare-phase helpers for typed save."""

from ...mutation_guard import ValidationProfile, capture_document_health
from ...save_service import DomainValidationError
from ._common import _rpc_mod
from .save_typed_helpers import marker_keys_for


def authorize_save_prepare(
    self,
    *,
    credential,
    document_identity,
    document,
    inflight,
):
    lease = _rpc_mod()._import_document_lease()
    record = _rpc_mod().document_lease_service.authorize(
        credential,
        selector={
            "document_session_uuid": document_identity.session_uuid,
            "document_name": document_identity.name,
        },
        allowed_states={
            lease.LeaseState.LOCKED_IDLE,
            lease.LeaseState.LOCKED_ERROR,
        },
    )
    self._touch_inflight_credential(credential, inflight)
    return record


def validate_save_references(document_identity):
    reference_preflight = _rpc_mod().inspect_references_gui(
        document_identity.name,
        only_invalid=True,
        validate=True,
    )
    if not reference_preflight.get("ok"):
        raise DomainValidationError(
            "Unable to inspect live document references before save",
            stage="live_reference_preflight",
            path=document_identity.canonical_path,
            mutation_may_have_occurred=False,
            details={"inspection": reference_preflight},
        )
    invalid_references = list(reference_preflight.get("references") or ())
    if invalid_references:
        raise DomainValidationError(
            (
                f"Typed save blocked by {len(invalid_references)} invalid "
                "live reference properties"
            ),
            stage="live_reference_preflight",
            path=document_identity.canonical_path,
            mutation_may_have_occurred=False,
            details={
                "invalid_count": len(invalid_references),
                "references": invalid_references[:100],
                "recomputed": False,
            },
        )


def begin_save_reservation(credential, mode, destination, phase):
    saving = _rpc_mod().document_lease_service.begin_save(credential)
    phase.update(
        saving_state_revision=saving.state_revision,
        saving_mutation_revision=saving.last_mutation_revision,
    )
    if mode == "save_as":
        if not destination:
            raise ValueError("Save As requires a destination")
        _rpc_mod().document_lease_service.reserve_save_as(credential, destination)
        phase["reserved"] = True
    elif mode != "save":
        raise ValueError(f"Unsupported save mode: {mode}")
    return saving


def populate_prepare_phase(
    phase,
    *,
    credential,
    document_identity,
    document,
    destination,
    validation_profile,
):
    phase.update(
        credential=credential,
        document_session_uuid=document_identity.session_uuid,
        document_name=document_identity.name,
        original_identity=document_identity,
        validation_expectations=_rpc_mod()._saved_document_expectations(document),
        source_path=(str(getattr(document, "FileName", "") or "") or None),
        health_before=capture_document_health(
            document,
            profile=ValidationProfile(str(validation_profile).lower()),
        ),
    )
    return marker_keys_for(document, document_identity, destination)
