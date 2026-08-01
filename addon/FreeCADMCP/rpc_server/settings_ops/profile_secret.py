"""Per-profile authentication secret provisioning."""

from __future__ import annotations

import contextlib
import os
import secrets
import sys
from pathlib import Path

from .migration import migrate
from .persistence import load_settings, save_settings


def _freecad():
    return sys.modules["FreeCAD"]


def ensure_profile_secret(settings=None):
    """Create the per-profile 256-bit authentication secret when configured.

    The function returns ``(settings, secret_path)`` and never exposes the
    secret value.  It is intentionally invoked by isolated-profile setup or by
    an explicit administrator action, not merely by importing the addon.
    """
    current = migrate(settings or load_settings())
    configured_secret = current.get("auth_secret_file")
    secret_path = Path(
        configured_secret
        or os.path.join(_freecad().getUserAppDataDir(), "freecad_mcp_auth.secret")
    )
    created = False
    if not secret_path.exists():
        secret_path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        fd = os.open(secret_path, flags, 0o600)
        try:
            os.write(fd, secrets.token_bytes(32))
            os.fsync(fd)
        finally:
            os.close(fd)
        created = True
    try:
        from document_lease.sidecar import _harden_permissions
    except ImportError:
        from addon.FreeCADMCP.document_lease.sidecar import _harden_permissions

    try:
        _harden_permissions(secret_path, strict=True)
    except Exception:
        if created:
            with contextlib.suppress(OSError):
                os.unlink(secret_path)
        raise
    current["auth_secret_file"] = str(secret_path)
    save_settings(current)
    return current, str(secret_path)
