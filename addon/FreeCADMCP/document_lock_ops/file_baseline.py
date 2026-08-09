from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path
from typing import Any

from .module_aliases import install_module_aliases


def file_baseline(file_path: str) -> tuple[float | None, str | None]:
    """Return (mtime, sha256 hex) for an on-disk FCStd, or (None, None)."""
    path = Path(file_path)
    if not path.is_file():
        return None, None
    try:
        st = path.stat()
        mtime = float(st.st_mtime)
        h = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                h.update(chunk)
        return mtime, h.hexdigest()
    except OSError:
        return None, None


def verify_saved_file(file_path: str, *, expect_hash: str | None = None) -> dict[str, Any]:
    path = Path(file_path)
    if not path.is_file():
        return {"ok": False, "error": "file_missing", "path": file_path}
    mtime, digest = file_baseline(file_path)
    if expect_hash is not None and digest != expect_hash:
        return {
            "ok": False,
            "error": "hash_mismatch",
            "path": file_path,
            "expected": expect_hash,
            "actual": digest,
        }
    return {"ok": True, "path": file_path, "mtime": mtime, "hash": digest}


def pid_alive_impl(pid: int) -> bool:
    """Best-effort liveness check (POSIX kill(0) / Windows OpenProcess)."""
    if pid is None or int(pid) <= 0:
        return False
    pid = int(pid)
    if sys.platform == "win32":
        try:
            import ctypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, pid
            )
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


pid_alive = pid_alive_impl

install_module_aliases(__name__)
