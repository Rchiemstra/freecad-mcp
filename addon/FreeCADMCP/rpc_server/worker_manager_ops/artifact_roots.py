"""Private artifact directories for one WorkerManager.

Every manager on a machine shares ``freecad_mcp_workers`` as its temp root.
The artifact directory used to be the single ``artifacts`` folder in that root,
so ``stop()`` on one FreeCAD instance deleted files another instance still
served, and either instance's expiry sweep did the same to the other's old
jobs. Each manager now owns a private directory and holds an exclusive lock
on a sibling lock file for as long as it is alive. Shutdown removes only that
directory. A peer removes an abandoned directory's expired jobs, and the
directory itself once nothing unexpired remains, only when the lock is free.
"""

from __future__ import annotations

import contextlib
import os
import re
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from ..worker_protocol_ops.constants import ARTIFACT_EXPIRY_SECONDS

_ARTIFACT_PREFIX = "mcp_artifacts_"
_LOCK_PREFIX = ".mcp_artifact_owner_"
_LOCK_SUFFIX = ".lock"
_TOKEN = re.compile(r"[0-9a-f]{32}\Z")


@dataclass
class ArtifactOwner:
    path: Path
    lock_path: Path
    lock_fd: int


def create_artifact_root(temp_root: Path) -> ArtifactOwner:
    """Create a directory no other manager can claim, then publish it."""

    token = uuid.uuid4().hex
    lock_path = _lock_path(temp_root, token)
    root = temp_root / f"{_ARTIFACT_PREFIX}{token}"
    flags = os.O_CREAT | os.O_EXCL | os.O_RDWR
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    fd = os.open(lock_path, flags, 0o600)
    try:
        os.write(fd, b"\0")
        _exclusive_lock(fd)
        root.mkdir(mode=0o700)
    except OSError:
        os.close(fd)
        lock_path.unlink(missing_ok=True)
        raise
    return ArtifactOwner(path=root, lock_path=lock_path, lock_fd=fd)


def release_artifact_root(owner: ArtifactOwner) -> None:
    """Remove this manager's artifact directory and its lock."""

    shutil.rmtree(owner.path, ignore_errors=True)
    fd = owner.lock_fd
    owner.lock_fd = -1
    if fd >= 0:
        _unlock(fd)
        with contextlib.suppress(OSError):
            os.close(fd)
    with contextlib.suppress(OSError):
        owner.lock_path.unlink(missing_ok=True)


def sweep_stale_artifacts(artifact_root: Path) -> None:
    """Delete job directories in one owned root that are older than an hour."""

    cutoff = time.time() - ARTIFACT_EXPIRY_SECONDS
    if not artifact_root.exists():
        return
    try:
        children = list(artifact_root.iterdir())
    except OSError:
        return
    for child in children:
        try:
            if child.stat().st_mtime < cutoff:
                shutil.rmtree(child, ignore_errors=True)
        except OSError:
            pass


def refresh_artifact_storage(temp_root: Path, artifact_root: Path) -> None:
    """Expire this manager's old jobs and reap abandoned peers."""

    sweep_stale_artifacts(artifact_root)
    reap_orphaned_artifact_roots(temp_root, artifact_root)


def reap_orphaned_artifact_roots(temp_root: Path, owned: Path) -> None:
    """Expire artifacts whose owner has released the lock, and drop empty roots."""

    owned_resolved = _resolve(owned)
    for child in _safe_glob(temp_root, f"{_ARTIFACT_PREFIX}*"):
        _reap_one(temp_root, child, owned_resolved)
    _reap_orphan_locks(temp_root)


def _reap_one(temp_root: Path, child: Path, owned_resolved: Path) -> None:
    token = _token_from_artifact_dir(child)
    if token is None:
        return
    try:
        if child.is_symlink() or not child.is_dir():
            return
        if child.resolve() == owned_resolved:
            return
    except OSError:
        return
    lock_path = _lock_path(temp_root, token)
    if not _lock_is_abandoned(lock_path):
        return
    sweep_stale_artifacts(child)
    if not _is_empty(child):
        return
    shutil.rmtree(child, ignore_errors=True)
    _unlink_if_abandoned(lock_path)


def _reap_orphan_locks(temp_root: Path) -> None:
    pattern = f"{_LOCK_PREFIX}*{_LOCK_SUFFIX}"
    for lock_path in _safe_glob(temp_root, pattern):
        token = _token_from_lock(lock_path)
        if token is None:
            continue
        root = temp_root / f"{_ARTIFACT_PREFIX}{token}"
        try:
            if root.exists():
                continue
        except OSError:
            continue
        _unlink_if_abandoned(lock_path)


def _lock_path(temp_root: Path, token: str) -> Path:
    return temp_root / f"{_LOCK_PREFIX}{token}{_LOCK_SUFFIX}"


def _token_from_artifact_dir(path: Path) -> str | None:
    if not path.name.startswith(_ARTIFACT_PREFIX):
        return None
    return _valid_token(path.name[len(_ARTIFACT_PREFIX) :])


def _token_from_lock(path: Path) -> str | None:
    name = path.name
    if not name.startswith(_LOCK_PREFIX) or not name.endswith(_LOCK_SUFFIX):
        return None
    token = name[len(_LOCK_PREFIX) : -len(_LOCK_SUFFIX)]
    return _valid_token(token)


def _valid_token(token: str) -> str | None:
    if _TOKEN.fullmatch(token) is None:
        return None
    return token


def _resolve(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path


def _safe_glob(root: Path, pattern: str) -> list[Path]:
    try:
        return list(root.glob(pattern))
    except OSError:
        return []


def _is_empty(root: Path) -> bool:
    try:
        next(root.iterdir())
    except StopIteration:
        return True
    except OSError:
        return False
    return False


def _unlink_if_abandoned(lock_path: Path) -> None:
    if not _lock_is_abandoned(lock_path):
        return
    with contextlib.suppress(OSError):
        lock_path.unlink(missing_ok=True)


def _lock_is_abandoned(lock_path: Path) -> bool:
    try:
        fd = os.open(lock_path, os.O_RDWR)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    acquired = False
    try:
        acquired = _try_exclusive_lock(fd)
        return acquired
    finally:
        if acquired:
            _unlock(fd)
        with contextlib.suppress(OSError):
            os.close(fd)


def _exclusive_lock(fd: int) -> None:
    if os.name == "nt":
        import msvcrt

        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        return
    import fcntl

    fcntl.flock(fd, fcntl.LOCK_EX)


def _try_exclusive_lock(fd: int) -> bool:
    if os.name == "nt":
        import msvcrt

        try:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True
    import fcntl

    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    return True


def _unlock(fd: int) -> None:
    if os.name == "nt":
        import msvcrt

        with contextlib.suppress(OSError):
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    with contextlib.suppress(OSError):
        fcntl.flock(fd, fcntl.LOCK_UN)
