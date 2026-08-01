"""MCP runtime identity and isolated-instance manifest loading."""

from __future__ import annotations

import json
import os
import socket
import stat
import uuid
from pathlib import Path

from ..rpc_auth_types.constants import (
    _PROCESS_STARTED_AT,
    MAX_INSTANCE_MANIFEST_BYTES,
)
from ..rpc_auth_types.instance_manifest import InstanceManifest
from ..rpc_auth_types.mcp_runtime_identity import McpRuntimeIdentity
from ..rpc_auth_types.rpc_auth_error import RpcAuthError
from ..rpc_auth_types.validation import _bounded_json, _format_utc


def make_mcp_runtime_identity(
    *,
    client_build_id: str,
    runtime_id: str | None = None,
    pid: int | None = None,
    process_started_at: str | None = None,
    hostname: str | None = None,
) -> McpRuntimeIdentity:
    """Create the immutable identity used for one MCP process lifetime."""

    return McpRuntimeIdentity(
        runtime_id=runtime_id or str(uuid.uuid4()),
        pid=os.getpid() if pid is None else pid,
        process_started_at=process_started_at or _format_utc(_PROCESS_STARTED_AT),
        hostname=hostname or socket.gethostname(),
        client_build_id=client_build_id,
    )


def load_instance_manifest(path: str | os.PathLike[str]) -> InstanceManifest:
    """Read a stable, bounded instance manifest without following a link."""

    manifest_path = Path(path)
    try:
        before = manifest_path.lstat()
    except OSError as exc:
        raise RpcAuthError(
            "INSTANCE_MANIFEST_UNAVAILABLE", "Instance manifest is unavailable"
        ) from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise RpcAuthError(
            "INSECURE_INSTANCE_MANIFEST", "Instance manifest must be a regular file"
        )
    if not 1 <= before.st_size <= MAX_INSTANCE_MANIFEST_BYTES:
        raise RpcAuthError(
            "MALFORMED_INSTANCE_MANIFEST", "Instance manifest has an invalid size"
        )
    try:
        with manifest_path.open("rb") as handle:
            raw = handle.read(MAX_INSTANCE_MANIFEST_BYTES + 1)
            after = os.fstat(handle.fileno())
    except OSError as exc:
        raise RpcAuthError(
            "INSTANCE_MANIFEST_UNAVAILABLE", "Instance manifest is unavailable"
        ) from exc
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise RpcAuthError(
            "INSTANCE_MANIFEST_CHANGED", "Instance manifest changed while loading"
        )
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RpcAuthError(
            "MALFORMED_INSTANCE_MANIFEST", "Instance manifest must contain UTF-8 JSON"
        ) from exc
    _bounded_json(payload, MAX_INSTANCE_MANIFEST_BYTES, "MALFORMED_INSTANCE_MANIFEST")
    manifest = InstanceManifest.from_dict(payload)
    profile_path = Path(manifest.profile_path)
    secret_path = Path(manifest.auth_secret_file)
    if not profile_path.is_absolute() or not secret_path.is_absolute():
        raise RpcAuthError(
            "INSECURE_INSTANCE_MANIFEST",
            "Isolated profile and authentication paths must be absolute",
        )
    resolved_profile = profile_path.resolve()
    if manifest_path.resolve().parent != resolved_profile:
        raise RpcAuthError(
            "INSECURE_INSTANCE_MANIFEST",
            "Instance manifest must reside at the isolated profile root",
        )
    try:
        secret_path.resolve().relative_to(resolved_profile)
    except ValueError as exc:
        raise RpcAuthError(
            "INSECURE_INSTANCE_MANIFEST",
            "Authentication secret must remain inside the isolated profile",
        ) from exc
    return manifest
