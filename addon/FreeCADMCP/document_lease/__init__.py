"""Frozen historic lease decoders and Phase 18 deprecation adapters."""

from .errors import (
    AuthorizationError,
    CleanReleaseError,
    CoordinationError,
    DirtyAcquisitionError,
    DirtyAdoptionError,
    DocumentIdentityRefreshEvent,
    ForeignRecoveryError,
    ForeignRecoveryRecord,
    LeaseConflictError,
    LeaseServiceError,
    LeaseStateError,
    LiveDocumentValidationError,
    LocalRecoveryError,
    LocalRuntimeIdentity,
    LockedErrorHandoffRequired,
    OrphanedForeignRecoveryRequired,
    OrphanedLocalMcpRecoveryRequired,
    ProcessLivenessEvidence,
    SavedForeignRecoveryRequired,
)
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
from .sidecar_types import (
    SidecarAtomicityError,
    SidecarCommitUncertainError,
    SidecarConflictError,
    SidecarError,
    SidecarExistsError,
    SidecarLockError,
    SidecarMalformedError,
    SidecarNetworkPathError,
    SidecarNotFoundError,
    SidecarPermissionError,
    SidecarTooLargeError,
)
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
