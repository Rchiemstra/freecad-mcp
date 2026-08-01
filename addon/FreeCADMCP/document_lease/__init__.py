"""FreeCAD-independent version-2 document lease core."""

from .identity import (  # noqa: F401 - public package re-exports
    DocumentIdentityError,
    DocumentIdentityService,
    DuplicateDocumentError,
    IdentityMismatchError,
    UnknownDocumentError,
    canonicalize_path,
    capture_file_baseline,
    file_identity_for_path,
)
from .model import (  # noqa: F401 - public package re-exports
    ALLOWED_TRANSITIONS,
    MAX_PERSISTED_TASK_SUMMARY_CHARS,
    RECORD_KIND,
    SCHEMA_VERSION,
    DocumentIdentity,
    DocumentSelector,
    FileBaseline,
    FileIdentity,
    InvalidTransitionError,
    LeaseCredential,
    LeaseErrorInfo,
    LeaseOwner,
    LeaseRecord,
    LeaseState,
    LiveDocumentValidation,
    SaveAsMigration,
    SaveAsMigrationRole,
    sanitize_persisted_task_summary,
    token_fingerprint,
    token_matches,
    validate_transition,
)
from .service import (  # noqa: F401 - public package re-exports
    AuthorizationError,
    CleanReleaseError,
    CoordinationError,
    DirtyAcquisitionError,
    DirtyAdoptionError,
    DocumentLeaseService,
    ForeignRecoveryError,
    ForeignRecoveryRecord,
    LeaseConflictError,
    LeaseGrant,
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
from .sidecar import (  # noqa: F401 - public package re-exports
    MAX_SIDECAR_BYTES,
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
    SidecarStore,
    SidecarTooLargeError,
    guard_path_for,
    parse_sidecar_bytes,
    sidecar_path_for,
    validate_sidecar_payload,
)

# Soft bridge to FreeCAD core mutation authority (optional import for callers).
try:
    from . import core_authority as core_authority
except Exception:  # pragma: no cover - keep package importable without FreeCAD
    core_authority = None  # type: ignore

__all__ = [name for name in globals() if not name.startswith("_")]
