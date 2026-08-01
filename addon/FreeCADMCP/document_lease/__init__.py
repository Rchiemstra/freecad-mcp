"""FreeCAD-independent version-2 document lease core."""

from .errors import *  # noqa: F403
from .errors import __all__ as _error_exports
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
from .model import LeaseRecord
from .service import DocumentLeaseService
from .sidecar import (  # noqa: F401 - public package re-exports
    MAX_SIDECAR_BYTES,
    SidecarStore,
    guard_path_for,
    parse_sidecar_bytes,
    sidecar_path_for,
    validate_sidecar_payload,
)
from .sidecar_types import (  # noqa: F401 - public package re-exports
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
from .sidecar_types import __all__ as _sidecar_type_exports
from .types import *  # noqa: F403
from .types import __all__ as _type_exports

# Soft bridge to FreeCAD core mutation authority (optional import for callers).
try:
    from . import core_authority as core_authority
except Exception:  # pragma: no cover - keep package importable without FreeCAD
    core_authority = None  # type: ignore

_identity_exports = [
    "DocumentIdentityError",
    "DocumentIdentityService",
    "DuplicateDocumentError",
    "IdentityMismatchError",
    "UnknownDocumentError",
    "canonicalize_path",
    "capture_file_baseline",
    "file_identity_for_path",
]

_sidecar_exports = [
    "MAX_SIDECAR_BYTES",
    "SidecarStore",
    "guard_path_for",
    "parse_sidecar_bytes",
    "sidecar_path_for",
    "validate_sidecar_payload",
]

__all__ = [
    *_identity_exports,
    *_type_exports,
    "LeaseRecord",
    "DocumentLeaseService",
    *_error_exports,
    *_sidecar_type_exports,
    *_sidecar_exports,
    "core_authority",
]
