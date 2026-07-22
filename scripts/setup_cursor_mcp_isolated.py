#!/usr/bin/env python3
"""Configure Cursor's ``freecad-isolated`` server from its instance manifest.

Only the ``freecad-isolated`` key is added or replaced.  An existing
``freecad`` key and every unrelated server are preserved exactly.  Endpoint
and identity values come from the profile manifest rather than being derived
independently from a port.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import ipaddress
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


ISOLATED_KEY = "freecad-isolated"
PROTECTED_KEY = "freecad"
PROFILE_NAME = ".freecad-mcp-isolated"
MANIFEST_FILENAME = "instance-manifest.json"
MANIFEST_SCHEMA_VERSION = 1
_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "rpc_host",
        "rpc_port",
        "profile_instance_id",
        "profile_path",
        "auth_secret_file",
        "expected_freecad_pid",
        "expected_freecad_process_started_at",
        "expected_addon_runtime_id",
        "expected_boot_id",
        "expected_protocol_version",
        "expected_protocol_features",
        "expected_addon_version",
        "expected_addon_build_id",
        "expected_freecad_version",
        "expected_freecad_revision",
        "expected_profile_path_fingerprint",
        "created_at",
    }
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _freecad_mcp_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_instance_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(
            f"Isolated instance manifest not found: {path}\n"
            "Run scripts/setup_isolated_profile.py first."
        ) from exc
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Cannot read isolated instance manifest {path}: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise SystemExit(f"Unsupported isolated instance manifest: {path}")
    if set(value) != _MANIFEST_FIELDS:
        missing_fields = sorted(_MANIFEST_FIELDS.difference(value))
        extra_fields = sorted(set(value).difference(_MANIFEST_FIELDS))
        raise SystemExit(
            "Invalid isolated manifest fields in "
            f"{path}: missing={missing_fields}, extra={extra_fields}"
        )

    required_strings = (
        "rpc_host",
        "profile_instance_id",
        "profile_path",
        "auth_secret_file",
        "created_at",
    )
    missing = [
        key
        for key in required_strings
        if not isinstance(value.get(key), str) or not value[key]
    ]
    port = value.get("rpc_port")
    if missing or isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        details = ", ".join(missing) if missing else "rpc_port"
        raise SystemExit(f"Invalid isolated manifest field(s) in {path}: {details}")

    try:
        rpc_address = ipaddress.ip_address(value["rpc_host"])
    except ValueError as exc:
        raise SystemExit(
            "Isolated rpc_host must be an explicit loopback IP address"
        ) from exc
    if not rpc_address.is_loopback:
        raise SystemExit(
            "Isolated rpc_host must remain on loopback; configure an SSH/TLS "
            "tunnel separately for remote workflows"
        )

    configured_profile = Path(value["profile_path"])
    if not configured_profile.is_absolute():
        raise SystemExit("profile_path in the isolated manifest must be absolute")
    profile_path = configured_profile.resolve()
    if path.resolve().parent != profile_path:
        raise SystemExit(
            "instance-manifest.json must reside at the root of its isolated profile"
        )
    configured_secret = Path(value["auth_secret_file"])
    if not configured_secret.is_absolute():
        raise SystemExit("auth_secret_file in the isolated manifest must be absolute")
    if configured_secret.is_symlink():
        raise SystemExit(
            f"Authentication secret must not be a symlink: {configured_secret}"
        )
    secret_path = configured_secret.resolve()
    try:
        secret_path.relative_to(profile_path)
    except ValueError as exc:
        raise SystemExit(
            "Authentication secret referenced by the manifest must remain inside "
            f"the isolated profile: {secret_path}"
        ) from exc
    try:
        secret_size = secret_path.stat().st_size
    except OSError as exc:
        raise SystemExit(
            f"Authentication secret referenced by the manifest is unavailable: {secret_path}"
        ) from exc
    if not secret_path.is_file() or secret_size != 32:
        raise SystemExit(
            f"Authentication secret must be a regular 32-byte file: {secret_path}"
        )
    return value


def _isolated_entry(
    python_exe: str,
    runner: Path,
    src_dir: Path,
    manifest_path: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    host = str(manifest["rpc_host"])
    port = int(manifest["rpc_port"])
    instance_id = str(manifest["profile_instance_id"])
    auth_file = str(manifest["auth_secret_file"])
    normalized_manifest = str(manifest_path.resolve()).replace("\\", "/")
    normalized_auth = str(Path(auth_file).resolve()).replace("\\", "/")
    return {
        "type": "stdio",
        "command": python_exe,
        "args": [
            str(runner).replace("\\", "/"),
            "--rpc-host",
            host,
            "--rpc-port",
            str(port),
            "--instance-id",
            instance_id,
            "--instance-manifest",
            normalized_manifest,
            "--auth-file",
            normalized_auth,
        ],
        "env": {
            "PYTHONUNBUFFERED": "1",
            "FREECAD_MCP_RPC_HOST": host,
            "FREECAD_MCP_PORT": str(port),
            "FREECAD_MCP_INSTANCE_ID": instance_id,
            "FREECAD_MCP_INSTANCE_MANIFEST": normalized_manifest,
            "FREECAD_MCP_AUTH_FILE": normalized_auth,
            "PYTHONPATH": str(src_dir).replace("\\", "/"),
        },
    }


def merge_isolated(path: Path, entry: dict[str, Any]) -> None:
    existing: dict[str, Any] = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise SystemExit(f"Cannot read Cursor MCP configuration {path}: {exc}") from exc
        if not isinstance(existing, dict):
            raise SystemExit(f"Cursor MCP configuration must be a JSON object: {path}")

    before = deepcopy(existing)
    previous_servers = existing.get("mcpServers", {})
    if not isinstance(previous_servers, dict):
        raise SystemExit(f"mcpServers must be a JSON object in {path}")
    servers = deepcopy(previous_servers)
    protected_before = deepcopy(servers.get(PROTECTED_KEY)) if PROTECTED_KEY in servers else None

    servers[ISOLATED_KEY] = entry
    merged = {**existing, "mcpServers": servers}

    after_protected = merged.get("mcpServers", {}).get(PROTECTED_KEY)
    if protected_before is not None and after_protected != protected_before:
        raise SystemExit(
            f"Abort: merge would modify protected key '{PROTECTED_KEY}' in {path}"
        )
    if PROTECTED_KEY in before.get("mcpServers", {}) and PROTECTED_KEY not in merged.get(
        "mcpServers", {}
    ):
        raise SystemExit(
            f"Abort: merge would remove protected key '{PROTECTED_KEY}' in {path}"
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(merged, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--instance-manifest",
        type=Path,
        default=None,
        help=(
            "Manifest created by setup_isolated_profile.py "
            f"(default: <repo>/{PROFILE_NAME}/{MANIFEST_FILENAME})"
        ),
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Deprecated assertion; must equal rpc_port in the manifest.",
    )
    parser.add_argument(
        "--instance-id",
        default=None,
        help="Deprecated assertion; must equal profile_instance_id in the manifest.",
    )
    args = parser.parse_args()

    repo = _repo_root()
    mcp_root = _freecad_mcp_root()
    runner = mcp_root / "scripts" / "run_freecad_mcp.py"
    if not runner.is_file():
        raise SystemExit(f"Runner not found: {runner}")

    manifest_path = (
        args.instance_manifest
        if args.instance_manifest is not None
        else repo / PROFILE_NAME / MANIFEST_FILENAME
    ).resolve()
    manifest = load_instance_manifest(manifest_path)
    if args.port is not None and args.port != manifest["rpc_port"]:
        raise SystemExit("--port does not match rpc_port in instance-manifest.json")
    if args.instance_id is not None and args.instance_id != manifest["profile_instance_id"]:
        raise SystemExit(
            "--instance-id does not match profile_instance_id in instance-manifest.json"
        )

    venv_py = mcp_root / ".venv" / "Scripts" / "python.exe"
    python_exe = str(venv_py) if venv_py.is_file() else sys.executable
    entry = _isolated_entry(
        python_exe.replace("\\", "/"),
        runner,
        mcp_root / "src",
        manifest_path,
        manifest,
    )
    config_path = repo / ".cursor" / "mcp.json"
    merge_isolated(config_path, entry)

    print(f"Updated {config_path}")
    print(f"  added/updated key: {ISOLATED_KEY}")
    print(f"  endpoint: {manifest['rpc_host']}:{manifest['rpc_port']}")
    print(f"  profile_instance_id: {manifest['profile_instance_id']}")
    print(f"  manifest: {manifest_path}")
    print(f"  protected key '{PROTECTED_KEY}' left unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
