"""Shared orphan-recovery validation helpers for document lease service ops."""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Callable
from typing import Any

from ..errors.coordination_error import CoordinationError
from ..errors.dirty_acquisition_error import DirtyAcquisitionError
from ..errors.dirty_adoption_error import DirtyAdoptionError
from ..errors.lease_service_error import LeaseServiceError
from ..errors.live_document_validation_error import LiveDocumentValidationError
from ..model import (
    FileBaseline,
    LeaseOwner,
    LiveDocumentValidation,
    token_fingerprint,
)


def validate_orphan_recovery_callbacks(
    *,
    authority_handoff: Callable[..., Any] | None,
    authority_rollback: Callable[..., Any] | None,
    credential_escrow: Callable[..., Any] | None,
) -> None:
    if (authority_handoff is None) != (authority_rollback is None):
        raise LeaseServiceError(
            "core authority handoff and rollback callbacks must be supplied together"
        )
    if credential_escrow is not None and authority_rollback is None:
        raise LeaseServiceError(
            "credential escrow requires an authority rollback callback"
        )


def assert_replacement_owner_runtime(
    self,
    owner: LeaseOwner,
) -> None:
    local = self._local_runtime_identity
    if local is None:
        raise CoordinationError("local runtime identity is unavailable")
    expected_runtime = (
        local.addon_profile_id,
        local.addon_runtime_id,
        local.freecad_pid,
        local.freecad_process_started_at,
        local.boot_id,
    )
    replacement_runtime = (
        owner.addon_profile_id,
        owner.addon_runtime_id,
        owner.freecad_pid,
        owner.freecad_process_started_at,
        owner.boot_id,
    )
    if replacement_runtime != expected_runtime:
        raise CoordinationError(
            "replacement owner does not belong to this FreeCAD runtime"
        )
    if (
        not local.hostname
        or not owner.hostname
        or local.hostname.casefold() != owner.hostname.casefold()
    ):
        raise CoordinationError("replacement owner does not belong to this host")


def validate_orphan_live_validation(
    validation: LiveDocumentValidation,
    identity,
    *,
    adopt_dirty: bool = False,
    local_confirmation: bool = False,
    require_clean: bool = False,
) -> None:
    if not isinstance(validation, LiveDocumentValidation):
        raise LiveDocumentValidationError(
            "fresh LiveDocumentValidation evidence is required"
        )
    if validation.document != identity:
        raise LiveDocumentValidationError(
            "live document evidence does not match the registered document"
        )
    if require_clean and validation.document_modified:
        raise DirtyAcquisitionError("orphan recovery requires a clean live document")
    if validation.document_modified and not adopt_dirty:
        raise DirtyAcquisitionError(
            "a pre-existing dirty document requires local adoption"
        )
    if adopt_dirty and local_confirmation is not True:
        raise DirtyAdoptionError(
            "dirty-document recovery requires explicit local GUI confirmation"
        )
    if adopt_dirty and not validation.document_modified:
        raise DirtyAdoptionError(
            "dirty-document recovery requires a currently dirty live document"
        )
    if validation.baseline_validated is not True:
        raise LiveDocumentValidationError(
            "orphan recovery requires a validated saved-file baseline"
        )
    if not isinstance(validation.baseline, FileBaseline):
        raise LiveDocumentValidationError(
            "orphan recovery requires a saved-file baseline"
        )


def validate_orphan_baseline_match(
    self,
    identity,
    validation: LiveDocumentValidation,
    previous_baseline: FileBaseline | None,
    *,
    mismatch_message: str,
) -> None:
    if validation.baseline != previous_baseline:
        raise LiveDocumentValidationError(mismatch_message)
    self._assert_current_baseline(
        identity,
        validation.baseline,
        error_type=LiveDocumentValidationError,
    )


def normalize_orphan_snapshot_id(snapshot_id: str) -> str:
    try:
        return str(uuid.UUID(str(snapshot_id)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise LeaseServiceError(
            "orphan recovery snapshot ID must be a UUID"
        ) from exc


def rotate_orphan_token_fingerprint(
    self,
    previous_fingerprint: str,
) -> tuple[str, str]:
    raw_token = self._token_factory()
    if not raw_token:
        raise LeaseServiceError("token factory returned an empty token")
    replacement_fingerprint = token_fingerprint(raw_token)
    if secrets.compare_digest(replacement_fingerprint, previous_fingerprint):
        raise LeaseServiceError("token factory did not rotate the fencing digest")
    return raw_token, replacement_fingerprint
