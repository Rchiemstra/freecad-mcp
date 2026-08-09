"""Frozen historic lease decoders and Phase 18 deprecation adapters."""

from .errors.authorization_error import AuthorizationError
from .errors.clean_release_error import CleanReleaseError
from .errors.coordination_error import CoordinationError
from .errors.dirty_acquisition_error import DirtyAcquisitionError
from .errors.dirty_adoption_error import DirtyAdoptionError
from .errors.document_identity_refresh_event import DocumentIdentityRefreshEvent
from .errors.foreign_recovery_error import ForeignRecoveryError
from .errors.foreign_recovery_record import ForeignRecoveryRecord
from .errors.lease_conflict_error import LeaseConflictError
from .errors.lease_service_error import LeaseServiceError
from .errors.lease_state_error import LeaseStateError
from .errors.live_document_validation_error import LiveDocumentValidationError
from .errors.local_recovery_error import LocalRecoveryError
from .errors.local_runtime_identity import LocalRuntimeIdentity
from .errors.locked_error_handoff_required import LockedErrorHandoffRequired
from .errors.orphaned_foreign_recovery_required import OrphanedForeignRecoveryRequired
from .errors.orphaned_local_mcp_recovery_required import OrphanedLocalMcpRecoveryRequired
from .errors.process_liveness_evidence import ProcessLivenessEvidence
from .errors.saved_foreign_recovery_required import SavedForeignRecoveryRequired
from .identity_helpers.path_canonicalize import canonicalize_path
from .identity_types.document_identity_error import DocumentIdentityError
from .identity_types.duplicate_document_error import DuplicateDocumentError
from .identity_types.identity_mismatch_error import IdentityMismatchError
from .identity_types.unknown_document_error import UnknownDocumentError
from .model import HistoricLeaseRecord, LeaseRecord, decode_historic_lease_record
from .service import DocumentLeaseService
from .sidecar import (
    GUARD_SUFFIX,
    MAX_SIDECAR_BYTES,
    SIDECAR_SUFFIX,
    decode_historic_sidecar_bytes,
    guard_path_for,
    parse_sidecar_bytes,
    sidecar_path_for,
    validate_sidecar_payload,
)
from .sidecar_types.sidecar_atomicity_error import SidecarAtomicityError
from .sidecar_types.sidecar_commit_uncertain_error import SidecarCommitUncertainError
from .sidecar_types.sidecar_conflict_error import SidecarConflictError
from .sidecar_types.sidecar_error import SidecarError
from .sidecar_types.sidecar_exists_error import SidecarExistsError
from .sidecar_types.sidecar_lock_error import SidecarLockError
from .sidecar_types.sidecar_malformed_error import SidecarMalformedError
from .sidecar_types.sidecar_network_path_error import SidecarNetworkPathError
from .sidecar_types.sidecar_not_found_error import SidecarNotFoundError
from .sidecar_types.sidecar_permission_error import SidecarPermissionError
from .sidecar_types.sidecar_too_large_error import SidecarTooLargeError
from .types.document_identity import DocumentIdentity
from .types.document_selector import DocumentSelector
from .types.file_baseline import FileBaseline
from .types.file_identity import FileIdentity
from .types.invalid_transition_error import InvalidTransitionError
from .types.lease_error_info import LeaseErrorInfo
from .types.lease_owner import LeaseOwner
from .types.lease_state import LeaseState
from .types.live_document_validation import LiveDocumentValidation
from .types.save_as_migration import SaveAsMigration
from .types.save_as_migration_role import SaveAsMigrationRole
from .types.schema_constants import (
    MAX_PERSISTED_TASK_SUMMARY_CHARS,
    RECORD_KIND,
    SCHEMA_VERSION,
)
from .types.task_summary import sanitize_persisted_task_summary
from .types.token_utils import token_fingerprint, token_matches
from .types.transitions import ALLOWED_TRANSITIONS, TERMINAL_STATES

__all__ = [
    "ALLOWED_TRANSITIONS",
    "GUARD_SUFFIX",
    "MAX_PERSISTED_TASK_SUMMARY_CHARS",
    "MAX_SIDECAR_BYTES",
    "RECORD_KIND",
    "SCHEMA_VERSION",
    "SIDECAR_SUFFIX",
    "TERMINAL_STATES",
    "AuthorizationError",
    "CleanReleaseError",
    "CoordinationError",
    "DirtyAcquisitionError",
    "DirtyAdoptionError",
    "DocumentIdentity",
    "DocumentIdentityError",
    "DocumentIdentityRefreshEvent",
    "DocumentLeaseService",
    "DocumentSelector",
    "DuplicateDocumentError",
    "FileBaseline",
    "FileIdentity",
    "ForeignRecoveryError",
    "ForeignRecoveryRecord",
    "HistoricLeaseRecord",
    "IdentityMismatchError",
    "InvalidTransitionError",
    "LeaseConflictError",
    "LeaseErrorInfo",
    "LeaseOwner",
    "LeaseRecord",
    "LeaseServiceError",
    "LeaseState",
    "LeaseStateError",
    "LiveDocumentValidation",
    "LiveDocumentValidationError",
    "LocalRecoveryError",
    "LocalRuntimeIdentity",
    "LockedErrorHandoffRequired",
    "OrphanedForeignRecoveryRequired",
    "OrphanedLocalMcpRecoveryRequired",
    "ProcessLivenessEvidence",
    "SaveAsMigration",
    "SaveAsMigrationRole",
    "SavedForeignRecoveryRequired",
    "SidecarAtomicityError",
    "SidecarCommitUncertainError",
    "SidecarConflictError",
    "SidecarError",
    "SidecarExistsError",
    "SidecarLockError",
    "SidecarMalformedError",
    "SidecarNetworkPathError",
    "SidecarNotFoundError",
    "SidecarPermissionError",
    "SidecarTooLargeError",
    "UnknownDocumentError",
    "canonicalize_path",
    "decode_historic_lease_record",
    "decode_historic_sidecar_bytes",
    "guard_path_for",
    "parse_sidecar_bytes",
    "sanitize_persisted_task_summary",
    "sidecar_path_for",
    "token_fingerprint",
    "token_matches",
    "validate_sidecar_payload",
]
