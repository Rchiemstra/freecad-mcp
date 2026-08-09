"""One-class save-service errors and result DTOs."""

from .archive_verification import ArchiveVerification
from .baseline_mismatch_error import BaselineMismatchError
from .baseline_required_error import BaselineRequiredError
from .destination_conflict_error import DestinationConflictError
from .document_dirty_error import DocumentDirtyError
from .domain_validation_error import DomainValidationError
from .fcstd_verification_error import FcstdVerificationError
from .finalize_result import FinalizeResult
from .invalid_save_request_error import InvalidSaveRequestError
from .lifecycle_callback_error import LifecycleCallbackError
from .save_invocation import SaveInvocation
from .save_invocation_error import SaveInvocationError
from .save_preflight import SavePreflight
from .save_result import SaveResult
from .save_service_error import SaveServiceError
from .saved_file_unstable_error import SavedFileUnstableError

__all__ = [
    "ArchiveVerification",
    "BaselineMismatchError",
    "BaselineRequiredError",
    "DestinationConflictError",
    "DocumentDirtyError",
    "DomainValidationError",
    "FcstdVerificationError",
    "FinalizeResult",
    "InvalidSaveRequestError",
    "LifecycleCallbackError",
    "SaveInvocation",
    "SaveInvocationError",
    "SavePreflight",
    "SaveResult",
    "SaveServiceError",
    "SavedFileUnstableError",
]
