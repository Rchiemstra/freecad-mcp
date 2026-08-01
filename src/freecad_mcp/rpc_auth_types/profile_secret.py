"""Profile secret loading for MCP RPC authentication."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from .constants import MAX_SECRET_FILE_BYTES, MIN_SECRET_BYTES
from .rpc_auth_error import RpcAuthError
from .validation import _validate_secret


def load_profile_secret(
    path: str | os.PathLike[str],
    *,
    require_owner_only: bool = True,
) -> bytes:
    """Load a bounded regular-file secret with the addon's safety checks."""

    secret_path = Path(path)
    try:
        before = secret_path.lstat()
    except OSError as exc:
        raise RpcAuthError(
            "PROFILE_SECRET_UNAVAILABLE", "Profile authentication secret is unavailable"
        ) from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise RpcAuthError(
            "INSECURE_PROFILE_SECRET",
            "Profile authentication secret must be a regular file",
        )
    if not MIN_SECRET_BYTES <= before.st_size <= MAX_SECRET_FILE_BYTES:
        raise RpcAuthError(
            "INVALID_PROFILE_SECRET",
            "Profile authentication secret has an invalid size",
        )
    if require_owner_only and os.name != "nt":
        if before.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
            raise RpcAuthError(
                "INSECURE_PROFILE_SECRET",
                "Profile authentication secret must be accessible only to its owner",
            )
        if hasattr(os, "geteuid") and before.st_uid != os.geteuid():
            raise RpcAuthError(
                "INSECURE_PROFILE_SECRET",
                "Profile authentication secret must be owned by the current user",
            )
    try:
        with secret_path.open("rb") as handle:
            value = handle.read(MAX_SECRET_FILE_BYTES + 1)
            after = os.fstat(handle.fileno())
    except OSError as exc:
        raise RpcAuthError(
            "PROFILE_SECRET_UNAVAILABLE", "Profile authentication secret is unavailable"
        ) from exc
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise RpcAuthError(
            "PROFILE_SECRET_CHANGED",
            "Profile authentication secret changed while loading",
        )
    return _validate_secret(value)
