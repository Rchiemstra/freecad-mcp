"""Pure compatibility facade for decoding retired lease sidecars.

The live sidecar store was removed when collaboration authority moved to the
native document revision stream.  The retained decoders, constants, errors, and
path calculators perform no filesystem access, locking, permission changes, CAS,
or writes.
"""

from __future__ import annotations

from .historic_sidecar import decode_historic_sidecar_bytes
from .sidecar_ops.codec import parse_sidecar_bytes
from .sidecar_ops.constants import GUARD_SUFFIX, MAX_SIDECAR_BYTES, SIDECAR_SUFFIX
from .sidecar_ops.paths import guard_path_for, sidecar_path_for
from .sidecar_ops.validate_payload import validate_sidecar_payload
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

__all__ = [
    "GUARD_SUFFIX",
    "MAX_SIDECAR_BYTES",
    "SIDECAR_SUFFIX",
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
    "decode_historic_sidecar_bytes",
    "guard_path_for",
    "parse_sidecar_bytes",
    "sidecar_path_for",
    "validate_sidecar_payload",
]
