#!/usr/bin/env python3
"""Create the private FreeCAD profile used by ``freecad-isolated``.

The profile owns one persistent random identity, a 256-bit authentication
secret and ``instance-manifest.json``.  The manifest is the shared source of
truth for the addon, launcher and MCP client; identities are never derived
from a port number.  The secret bytes are stored separately and are never
serialized into settings, the manifest, or Cursor configuration.

The script refuses to write below the normal AppData FreeCAD profile so the
existing ``freecad`` MCP instance remains untouched.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import secrets
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any


ISOLATED_PORT = 9876
RPC_HOST = "127.0.0.1"
PROFILE_NAME = ".freecad-mcp-isolated"
MANIFEST_FILENAME = "instance-manifest.json"
SECRET_FILENAME = "freecad_mcp_auth.secret"
SETTINGS_FILENAME = "freecad_mcp_settings.json"
MANIFEST_SCHEMA_VERSION = 1


def _repo_root() -> Path:
    # scripts/ -> freecad-mcp/ -> mcp/ -> tools/ -> FreeCAD repo
    return Path(__file__).resolve().parents[4]


def _freecad_mcp_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _appdata_freecad() -> Path:
    appdata = os.environ.get("APPDATA") or ""
    return Path(appdata) / "FreeCAD" if appdata else Path()


def _ensure_not_appdata(path: Path) -> None:
    app = _appdata_freecad()
    if not app or not app.exists():
        return
    try:
        path.resolve().relative_to(app.resolve())
    except ValueError:
        return
    raise SystemExit(
        f"Refusing to install isolated profile under AppData FreeCAD: {path}"
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Cannot read valid JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"Expected a JSON object in {path}")
    return value


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        os.replace(temporary, path)
    except Exception:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise


def _validate_profile_id(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise SystemExit("profile_instance_id must be a UUID")
    candidate = value.removeprefix("freecad-isolated-")
    try:
        return str(uuid.UUID(candidate))
    except (ValueError, AttributeError) as exc:
        raise SystemExit("profile_instance_id must be a UUID") from exc


def _persistent_profile_id(
    profile: Path, requested: str | None = None
) -> tuple[str, dict[str, Any] | None]:
    manifest_path = profile / MANIFEST_FILENAME
    settings_path = profile / SETTINGS_FILENAME
    existing_manifest = (
        _load_json_object(manifest_path) if manifest_path.is_file() else None
    )
    existing_id: str | None = None
    if existing_manifest is not None:
        if existing_manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
            raise SystemExit(
                f"Unsupported isolated manifest schema in {manifest_path}"
            )
        existing_id = _validate_profile_id(
            existing_manifest.get("profile_instance_id")
        )
    elif settings_path.is_file():
        settings = _load_json_object(settings_path)
        candidate = settings.get("profile_instance_id") or settings.get("instance_id")
        if candidate:
            existing_id = _validate_profile_id(candidate)

    requested_id = _validate_profile_id(requested) if requested else None
    if existing_id and requested_id and existing_id != requested_id:
        raise SystemExit(
            "Refusing to replace the persistent isolated profile identity: "
            f"existing={existing_id!r}, requested={requested_id!r}"
        )
    profile_id = existing_id or requested_id or str(uuid.uuid4())
    return profile_id, existing_manifest


def _restrict_owner_only(path: Path) -> None:
    """Make *path* owner-only, failing closed when Windows ACL setup fails."""

    try:
        os.chmod(path, 0o600)
    except OSError as exc:
        raise SystemExit(f"Cannot restrict authentication secret {path}: {exc}") from exc
    if sys.platform != "win32":
        return

    try:
        whoami = subprocess.run(
            ["whoami"], check=True, capture_output=True, text=True
        ).stdout.strip()
        if not whoami:
            raise RuntimeError("whoami returned no account")
        subprocess.run(
            [
                "icacls",
                str(path),
                "/inheritance:r",
                "/grant:r",
                f"{whoami}:(F)",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError, RuntimeError) as exc:
        raise SystemExit(
            f"Cannot apply an owner-only Windows ACL to {path}: {exc}"
        ) from exc


def _ensure_auth_secret(path: Path) -> Path:
    """Create or validate the profile's raw 32-byte authentication secret."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file():
            raise SystemExit(f"Authentication secret must be a regular file: {path}")
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise SystemExit(f"Cannot inspect authentication secret {path}: {exc}") from exc
        if size != 32:
            raise SystemExit(
                f"Authentication secret must contain exactly 32 bytes: {path}"
            )
        _restrict_owner_only(path)
        return path.resolve()

    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise SystemExit(f"Cannot create authentication secret {path}: {exc}") from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(secrets.token_bytes(32))
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            path.unlink()
        except OSError:
            pass
        raise
    _restrict_owner_only(path)
    return path.resolve()


def _profile_secret_path(
    profile: Path, existing_manifest: dict[str, Any] | None
) -> Path:
    configured = (existing_manifest or {}).get("auth_secret_file")
    candidate = Path(configured) if isinstance(configured, str) and configured else (
        profile / SECRET_FILENAME
    )
    if not candidate.is_absolute():
        candidate = profile / candidate
    if candidate.is_symlink():
        raise SystemExit(f"Authentication secret must not be a symlink: {candidate}")
    resolved = candidate.resolve()
    try:
        resolved.relative_to(profile.resolve())
    except ValueError as exc:
        raise SystemExit(
            "The isolated authentication secret must remain inside its private profile: "
            f"{resolved}"
        ) from exc
    return resolved


def _build_manifest(
    *,
    profile: Path,
    profile_id: str,
    secret_path: Path,
    rpc_port: int,
    existing: dict[str, Any] | None,
) -> dict[str, Any]:
    existing = existing or {}
    same_endpoint = (
        existing.get("rpc_host") == RPC_HOST
        and existing.get("rpc_port") == rpc_port
        and existing.get("profile_instance_id") == profile_id
    )
    runtime_fields = (
        {
            key: existing.get(key)
            for key in (
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
            )
        }
        if same_endpoint
        else {
            "expected_freecad_pid": None,
            "expected_freecad_process_started_at": None,
            "expected_addon_runtime_id": None,
            "expected_boot_id": None,
            "expected_protocol_version": None,
            "expected_protocol_features": None,
            "expected_addon_version": None,
            "expected_addon_build_id": None,
            "expected_freecad_version": None,
            "expected_freecad_revision": None,
            "expected_profile_path_fingerprint": None,
        }
    )
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "rpc_host": RPC_HOST,
        "rpc_port": rpc_port,
        "profile_instance_id": profile_id,
        "profile_path": str(profile.resolve()),
        "auth_secret_file": str(secret_path.resolve()),
        **runtime_fields,
        "created_at": existing.get("created_at") or _utc_now(),
    }


def _junction(src: Path, dst: Path) -> None:
    if dst.exists() or dst.is_symlink():
        if sys.platform == "win32":
            # rmdir removes a junction without deleting target contents.
            subprocess.run(["cmd", "/c", "rmdir", str(dst)], check=False)
            if dst.exists():
                import shutil

                shutil.rmtree(dst)
        elif dst.is_symlink() or dst.is_file():
            dst.unlink()
        else:
            import shutil

            shutil.rmtree(dst)

    dst.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        completed = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(dst), str(src)],
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise SystemExit(
                f"Failed to create junction {dst} -> {src}:\n"
                f"{completed.stdout}\n{completed.stderr}"
            )
    else:
        dst.symlink_to(src, target_is_directory=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--port",
        type=int,
        default=ISOLATED_PORT,
        help=f"RPC port for the isolated addon (default: {ISOLATED_PORT})",
    )
    parser.add_argument(
        "--instance-id",
        default=None,
        help=(
            "Compatibility override for first setup only. Reruns must match the "
            "persistent profile_instance_id stored in instance-manifest.json."
        ),
    )
    args = parser.parse_args()
    port = int(args.port)
    if not 1 <= port <= 65535:
        raise SystemExit("RPC port must be between 1 and 65535")

    repo = _repo_root()
    mcp_root = _freecad_mcp_root()
    addon_src = mcp_root / "addon" / "FreeCADMCP"
    if not addon_src.is_dir():
        raise SystemExit(f"Addon source not found: {addon_src}")

    profile = repo / PROFILE_NAME
    _ensure_not_appdata(profile)
    profile_id, existing_manifest = _persistent_profile_id(profile, args.instance_id)

    mod_dir = profile / "Mod"
    temp_dir = profile / "temp"
    recovery_dir = profile / "lease-recovery"
    for directory in (mod_dir, temp_dir, recovery_dir):
        directory.mkdir(parents=True, exist_ok=True)

    addon_dst = mod_dir / "FreeCADMCP"
    _junction(addon_src, addon_dst)

    secret_path = _ensure_auth_secret(
        _profile_secret_path(profile, existing_manifest)
    )
    manifest = _build_manifest(
        profile=profile,
        profile_id=profile_id,
        secret_path=secret_path,
        rpc_port=port,
        existing=existing_manifest,
    )
    manifest_path = profile / MANIFEST_FILENAME
    _atomic_write_json(manifest_path, manifest)

    settings = {
        "remote_enabled": False,
        "allowed_ips": "127.0.0.1",
        "auto_start_rpc": True,
        "rpc_bind_host": RPC_HOST,
        "rpc_port": port,
        "freecadcmd_path": str(
            repo / "build" / "release" / "bin" / "FreeCADCmd.exe"
        ),
        "allow_remote_execute_code": False,
        "allow_authenticated_remote_without_transport_security": False,
        "profile_instance_id": profile_id,
        # Kept for v1 identity checks during the compatibility window.
        "instance_id": profile_id,
        "auth_secret_file": str(secret_path),
        "document_lease_mode": "enforce",
        "allow_network_sidecar": False,
        "persist_task_summary_in_sidecar": False,
        "allow_unsafe_mutating_execute_code": False,
        "enable_document_lock": True,
        "document_lock_enforcement": True,
    }
    settings_path = profile / SETTINGS_FILENAME
    _atomic_write_json(settings_path, settings)

    report = {
        "profile": str(profile),
        "addon": str(addon_dst),
        "settings": str(settings_path),
        "manifest": str(manifest_path),
        "auth_secret_file": str(secret_path),
        "rpc_endpoint": f"{RPC_HOST}:{port}",
        "profile_instance_id": profile_id,
        "freecad_exe": str(repo / "build" / "release" / "bin" / "FreeCAD.exe"),
    }
    print("Isolated FreeCAD MCP profile ready:")
    for key, value in report.items():
        print(f"  {key}: {value}")
    print("  auth_secret: <stored separately; contents not printed>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
