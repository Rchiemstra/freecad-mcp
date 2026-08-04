"""Guarded, schema-validated persistence for adjacent lease sidecars."""

from __future__ import annotations

import contextlib
import os
from collections.abc import Callable
from pathlib import Path

from .historic_sidecar import decode_historic_sidecar_bytes
from .model import LeaseRecord
from .sidecar_ops.cas import matches_cas
from .sidecar_ops.codec import parse_sidecar_bytes, serialize_record
from .sidecar_ops.constants import GUARD_SUFFIX, MAX_SIDECAR_BYTES, SIDECAR_SUFFIX
from .sidecar_ops.fsync_directory import fsync_directory
from .sidecar_ops.guard import (
    _process_locks,  # noqa: F401
    _process_locks_guard,  # noqa: F401
    lock_windows,
    open_guard,
    process_lock,
    unlock_windows,
)
from .sidecar_ops.guard import (
    native_guard as _native_guard,
)
from .sidecar_ops.io import assert_regular_not_symlink, read_record, write_temp
from .sidecar_ops.network_path import is_network_path
from .sidecar_ops.paths import guard_path_for, sidecar_path_for
from .sidecar_ops.permissions import (
    assert_windows_owner_only,
    harden_directory_permissions,
    harden_owner_only,
    harden_permissions,
)
from .sidecar_ops.schema_expect import (
    expect_bool,
    expect_int,
    expect_keys,
    expect_string,
    expect_timestamp,
    expect_uuid,
    validate_file_identity,
)
from .sidecar_ops.validate_payload import validate_sidecar_payload
from .sidecar_ops.windows_dacl_inspect import inspect_windows_owner_only
from .sidecar_ops.windows_dacl_set import set_windows_owner_only
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

# §3.3 shims — preserve legacy import paths and test monkeypatch targets.
_is_network_path = is_network_path
_assert_regular_not_symlink = assert_regular_not_symlink
_fsync_directory = fsync_directory
_read_record = read_record
_write_temp = write_temp
_serialize_record = serialize_record
_matches_cas = matches_cas
_process_lock = process_lock
_open_guard = open_guard
_lock_windows = lock_windows
_unlock_windows = unlock_windows
_expect_keys = expect_keys
_expect_string = expect_string
_expect_int = expect_int
_expect_bool = expect_bool
_expect_uuid = expect_uuid
_expect_timestamp = expect_timestamp
_validate_file_identity = validate_file_identity
_assert_windows_owner_only = assert_windows_owner_only
_harden_owner_only = harden_owner_only
_harden_permissions = harden_permissions
_harden_directory_permissions = harden_directory_permissions
_inspect_windows_owner_only = inspect_windows_owner_only
_set_windows_owner_only = set_windows_owner_only

from .sidecar_ops.store_create import create_sidecar  # noqa: E402
from .sidecar_ops.store_delete import delete_sidecar  # noqa: E402
from .sidecar_ops.store_replace import replace_sidecar  # noqa: E402


class SidecarStore:
    """Atomic guarded create/replace/delete with strict compare-and-swap."""

    def __init__(
        self,
        *,
        max_bytes: int = MAX_SIDECAR_BYTES,
        strict_permissions: bool = True,
        allow_network: bool = False,
        persist_task_summary: bool = False,
        network_detector: Callable[[Path], bool] = is_network_path,
    ) -> None:
        if not isinstance(persist_task_summary, bool):
            raise TypeError("persist_task_summary must be true or false")
        self.max_bytes = max_bytes
        self.strict_permissions = strict_permissions
        self.allow_network = allow_network
        self.persist_task_summary = persist_task_summary
        self.network_detector = network_detector

    def _check_target(self, path: Path) -> None:
        if self.network_detector(path) and not self.allow_network:
            raise SidecarNetworkPathError(
                f"network sidecars require an explicit lower-assurance override: {path}"
            )
        if not path.parent.is_dir():
            raise SidecarError(f"sidecar parent directory does not exist: {path.parent}")

    def guard(self, path: str | os.PathLike[str]) -> contextlib.AbstractContextManager[None]:
        sidecar = Path(path)
        self._check_target(sidecar)
        return _native_guard(
            guard_path_for(sidecar), strict_permissions=self.strict_permissions
        )

    def read(self, path: str | os.PathLike[str]) -> LeaseRecord:
        sidecar = Path(path)
        self._check_target(sidecar)
        return _read_record(
            sidecar,
            max_bytes=self.max_bytes,
            strict_permissions=self.strict_permissions,
        )

    def create(self, path: str | os.PathLike[str], record: LeaseRecord) -> None:
        sidecar = Path(path)
        self._check_target(sidecar)
        create_sidecar(
            sidecar,
            record,
            max_bytes=self.max_bytes,
            strict_permissions=self.strict_permissions,
            persist_task_summary=self.persist_task_summary,
        )

    def replace(
        self,
        path: str | os.PathLike[str],
        record: LeaseRecord,
        *,
        expected: LeaseRecord,
    ) -> None:
        sidecar = Path(path)
        self._check_target(sidecar)
        replace_sidecar(
            sidecar,
            record,
            expected=expected,
            max_bytes=self.max_bytes,
            strict_permissions=self.strict_permissions,
            persist_task_summary=self.persist_task_summary,
        )

    def delete(
        self, path: str | os.PathLike[str], *, expected: LeaseRecord
    ) -> None:
        sidecar = Path(path)
        self._check_target(sidecar)
        delete_sidecar(
            sidecar,
            expected=expected,
            max_bytes=self.max_bytes,
            strict_permissions=self.strict_permissions,
        )


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
    "SidecarStore",
    "SidecarTooLargeError",
    "decode_historic_sidecar_bytes",
    "guard_path_for",
    "parse_sidecar_bytes",
    "sidecar_path_for",
    "validate_sidecar_payload",
]
