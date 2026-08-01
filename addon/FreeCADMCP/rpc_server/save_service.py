"""Typed, fail-closed FCStd save and finalization helpers.

The public functions in this module deliberately have no import-time FreeCAD
dependency.  A live ``App::Document`` proxy is supplied by the RPC layer after
the request has been authorized and revalidated on FreeCAD's GUI thread.

This service owns filesystem preflight and post-save verification.  It does
not own lease state: callers should enter ``LOCKED_SAVING`` before invoking it,
record any :class:`SaveServiceError` as ``LOCKED_ERROR``, and pass lease-owned
callbacks to :meth:`SaveService.finalize_document_edit` when a verified save
should be followed by guarded release.
"""

from __future__ import annotations

from .save_service_ops.archive import verify_fcstd_archive
from .save_service_ops.baseline import compare_file_to_baseline
from .save_service_ops.service_class import SaveService

# §3.3 compatibility shims — moved symbols keep their legacy import path.
from .save_types.archive_verification import ArchiveVerification
from .save_types.baseline_mismatch_error import BaselineMismatchError
from .save_types.baseline_required_error import BaselineRequiredError
from .save_types.destination_conflict_error import DestinationConflictError
from .save_types.document_dirty_error import DocumentDirtyError
from .save_types.domain_validation_error import DomainValidationError
from .save_types.fcstd_verification_error import FcstdVerificationError
from .save_types.finalize_result import FinalizeResult
from .save_types.invalid_save_request_error import InvalidSaveRequestError
from .save_types.lifecycle_callback_error import LifecycleCallbackError
from .save_types.save_invocation import SaveInvocation
from .save_types.save_invocation_error import SaveInvocationError
from .save_types.save_preflight import SavePreflight
from .save_types.save_result import SaveResult
from .save_types.save_service_error import SaveServiceError
from .save_types.saved_file_unstable_error import SavedFileUnstableError

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
    "SaveService",
    "SaveServiceError",
    "SavedFileUnstableError",
    "compare_file_to_baseline",
    "verify_fcstd_archive",
]
