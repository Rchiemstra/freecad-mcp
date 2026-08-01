"""One-class document lease service errors and DTOs."""

from .authorization_error import AuthorizationError
from .clean_release_error import CleanReleaseError
from .coordination_error import CoordinationError
from .dirty_acquisition_error import DirtyAcquisitionError
from .dirty_adoption_error import DirtyAdoptionError
from .document_identity_refresh_event import DocumentIdentityRefreshEvent
from .foreign_recovery_error import ForeignRecoveryError
from .foreign_recovery_record import ForeignRecoveryRecord
from .lease_conflict_error import LeaseConflictError
from .lease_grant import LeaseGrant
from .lease_service_error import LeaseServiceError
from .lease_state_error import LeaseStateError
from .live_document_validation_error import LiveDocumentValidationError
from .local_recovery_error import LocalRecoveryError
from .local_runtime_identity import LocalRuntimeIdentity
from .locked_error_handoff_required import LockedErrorHandoffRequired
from .orphaned_foreign_recovery_required import OrphanedForeignRecoveryRequired
from .orphaned_local_mcp_recovery_required import OrphanedLocalMcpRecoveryRequired
from .process_liveness_evidence import ProcessLivenessEvidence
from .saved_foreign_recovery_required import SavedForeignRecoveryRequired

__all__ = [
    "AuthorizationError",
    "CleanReleaseError",
    "CoordinationError",
    "DirtyAcquisitionError",
    "DirtyAdoptionError",
    "DocumentIdentityRefreshEvent",
    "ForeignRecoveryError",
    "ForeignRecoveryRecord",
    "LeaseConflictError",
    "LeaseGrant",
    "LeaseServiceError",
    "LeaseStateError",
    "LiveDocumentValidationError",
    "LocalRecoveryError",
    "LocalRuntimeIdentity",
    "LockedErrorHandoffRequired",
    "OrphanedForeignRecoveryRequired",
    "OrphanedLocalMcpRecoveryRequired",
    "ProcessLivenessEvidence",
    "SavedForeignRecoveryRequired",
]
