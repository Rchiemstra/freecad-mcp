"""Profile authentication secret load and create helpers."""

from __future__ import annotations

import contextlib
import os
import secrets
import stat
from pathlib import Path

from .constants import MAX_SECRET_FILE_BYTES, MIN_SECRET_BYTES
from .protocol_error import ProtocolError
from .validation import _validate_secret


def load_profile_secret(
    path: str | os.PathLike[str],
    *,
    require_owner_only: bool = True,
) -> bytes:
    """Load a bounded regular-file secret and enforce POSIX ownership/mode.

    Python's standard library does not provide a portable Windows DACL reader.
    On Windows this function still rejects links, non-regular files, and unsafe
    sizes; the profile setup code must create an owner-only DACL.
    """

    secret_path = Path(path)
    try:
        before = secret_path.lstat()
    except OSError as exc:
        raise ProtocolError(
            "PROFILE_SECRET_UNAVAILABLE", "Profile authentication secret is unavailable"
        ) from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise ProtocolError(
            "INSECURE_PROFILE_SECRET", "Profile authentication secret must be a regular file"
        )
    if not MIN_SECRET_BYTES <= before.st_size <= MAX_SECRET_FILE_BYTES:
        raise ProtocolError(
            "INVALID_PROFILE_SECRET", "Profile authentication secret has an invalid size"
        )
    if require_owner_only and os.name != "nt":
        if before.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
            raise ProtocolError(
                "INSECURE_PROFILE_SECRET",
                "Profile authentication secret must be accessible only to its owner",
            )
        if hasattr(os, "geteuid") and before.st_uid != os.geteuid():
            raise ProtocolError(
                "INSECURE_PROFILE_SECRET",
                "Profile authentication secret must be owned by the current user",
            )
    try:
        with secret_path.open("rb") as handle:
            value = handle.read(MAX_SECRET_FILE_BYTES + 1)
            after = os.fstat(handle.fileno())
    except OSError as exc:
        raise ProtocolError(
            "PROFILE_SECRET_UNAVAILABLE", "Profile authentication secret is unavailable"
        ) from exc
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise ProtocolError(
            "PROFILE_SECRET_CHANGED", "Profile authentication secret changed while loading"
        )
    return _validate_secret(value)


def create_profile_secret(
    path: str | os.PathLike[str],
    *,
    num_bytes: int = 32,
) -> bytes:
    """Create a new secret without overwriting an existing profile secret."""

    if not MIN_SECRET_BYTES <= num_bytes <= MAX_SECRET_FILE_BYTES:
        raise ProtocolError(
            "INVALID_PROFILE_SECRET", "Requested profile secret size is invalid"
        )
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    value = secrets.token_bytes(num_bytes)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    try:
        descriptor = os.open(target, flags, 0o600)
    except OSError as exc:
        raise ProtocolError(
            "PROFILE_SECRET_CREATE_FAILED",
            "Profile authentication secret could not be created",
        ) from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        if os.name != "nt":
            os.chmod(target, 0o600)
    except Exception:
        with contextlib.suppress(OSError):
            target.unlink()
        raise
    return value
