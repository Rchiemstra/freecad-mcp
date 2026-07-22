#!/usr/bin/env python3
"""Launch FreeCAD with the isolated MCP profile and prove its RPC identity.

The launcher refuses an already occupied endpoint.  It starts one FreeCAD
process, uses ``get_instance_info`` only to discover the candidate runtime,
then accepts readiness only after a profile-secret-authenticated v2 handshake
proves the launched PID, persistent profile identity, endpoint, runtime UUID,
process start, version and build metadata.  It never stops or reuses a process
already listening on the configured endpoint, including the default :9875
instance.
"""
from __future__ import annotations

import hashlib
import importlib.util
import ipaddress
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import uuid
import xmlrpc.client
from pathlib import Path
from typing import Any


# The launcher is run directly from ``scripts/`` as well as from an installed
# package.  Put this checkout's ``src`` first so its authentication codec is
# exactly the one paired with the addon being launched.
_MCP_SOURCE = Path(__file__).resolve().parents[1] / "src"
if str(_MCP_SOURCE) not in sys.path:
    sys.path.insert(0, str(_MCP_SOURCE))

from freecad_mcp.rpc_auth import (  # noqa: E402
    McpRuntimeIdentity,
    PROTOCOL_VERSION,
    REQUIRED_PROTOCOL_FEATURES,
    RpcAuthError,
    build_handshake_request,
    load_profile_secret,
    make_mcp_runtime_identity,
    verify_handshake_response,
)


PROFILE_NAME = ".freecad-mcp-isolated"
MANIFEST_FILENAME = "instance-manifest.json"
MANIFEST_SCHEMA_VERSION = 1
LAUNCHER_BUILD_ID = "freecad-mcp-isolated-launcher-0.1.20"
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


class InstanceValidationError(RuntimeError):
    """The endpoint answered, but it is not the launched isolated runtime."""


class _TimeoutTransport(xmlrpc.client.Transport):
    def __init__(self, timeout: float = 2.0) -> None:
        super().__init__()
        self.timeout = timeout

    def make_connection(self, host):
        connection = super().make_connection(host)
        connection.timeout = self.timeout
        return connection


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _manifest_path(profile: Path) -> Path:
    return profile / MANIFEST_FILENAME


def _load_manifest(profile: Path) -> dict[str, Any]:
    path = _manifest_path(profile)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(
            f"Isolated manifest missing: {path}\n"
            "Run scripts/setup_isolated_profile.py first."
        ) from exc
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Cannot read isolated manifest {path}: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise SystemExit(f"Unsupported isolated manifest: {path}")
    if set(value) != _MANIFEST_FIELDS:
        missing = sorted(_MANIFEST_FIELDS.difference(value))
        extra = sorted(set(value).difference(_MANIFEST_FIELDS))
        raise SystemExit(
            f"Invalid isolated manifest fields in {path}: missing={missing}, extra={extra}"
        )
    for field in (
        "rpc_host",
        "profile_instance_id",
        "profile_path",
        "auth_secret_file",
        "created_at",
    ):
        if not isinstance(value.get(field), str) or not value[field]:
            raise SystemExit(f"Invalid {field} in isolated manifest: {path}")
    port = value.get("rpc_port")
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise SystemExit(f"Invalid rpc_port in isolated manifest: {path}")
    try:
        rpc_address = ipaddress.ip_address(value["rpc_host"])
    except ValueError as exc:
        raise SystemExit(
            "Isolated rpc_host must be an explicit loopback IP address"
        ) from exc
    if not rpc_address.is_loopback:
        raise SystemExit(
            "Isolated rpc_host must remain on loopback; use a local SSH/TLS "
            "tunnel endpoint for remote workflows"
        )
    if not Path(value["profile_path"]).is_absolute():
        raise SystemExit(f"profile_path must be absolute in isolated manifest: {path}")
    if _normalize_path(value["profile_path"]) != _normalize_path(profile):
        raise SystemExit(f"profile_path does not identify {profile}: {path}")
    configured_secret = Path(value["auth_secret_file"])
    if not configured_secret.is_absolute():
        raise SystemExit(f"auth_secret_file must be absolute in isolated manifest: {path}")
    if configured_secret.is_symlink():
        raise SystemExit(
            f"Authentication secret must not be a symlink: {configured_secret}"
        )
    secret_path = configured_secret.resolve()
    try:
        secret_path.relative_to(profile.resolve())
    except ValueError as exc:
        raise SystemExit(
            f"Authentication secret must remain inside isolated profile: {secret_path}"
        ) from exc
    try:
        secret_size = secret_path.stat().st_size
    except OSError as exc:
        raise SystemExit(f"Authentication secret is unavailable: {secret_path}") from exc
    if not secret_path.is_file() or secret_size != 32:
        raise SystemExit(
            f"Authentication secret must be a regular 32-byte file: {secret_path}"
        )
    return value


def _write_manifest(profile: Path, value: dict[str, Any]) -> None:
    path = _manifest_path(profile)
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


def _reserve_endpoint(host: str, port: int) -> socket.socket:
    """Exclusively bind the endpoint without contacting an existing listener.

    The returned socket is intentionally not put into listening mode.  Holding
    the bind closes the preflight check/use window while launch arguments and
    environment are prepared.  The launcher releases it immediately before
    spawning FreeCAD because the addon cannot inherit an already-bound socket.
    """

    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    reservation = socket.socket(family, socket.SOCK_STREAM)
    try:
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            reservation.setsockopt(
                socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1
            )
        else:
            reservation.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        reservation.bind((host, port))
    except OSError as exc:
        reservation.close()
        raise SystemExit(
            f"Refusing to start isolated FreeCAD: {host}:{port} is already occupied. "
            "The existing process was not contacted, probed, reused, or stopped."
        ) from exc
    return reservation


def _normalize_path(value: object) -> str:
    return os.path.normcase(os.path.realpath(os.path.abspath(str(value))))


def _freecad_build_identity(value: object) -> tuple[str, str]:
    parts = list(value) if isinstance(value, (list, tuple)) else [value]
    rendered = [str(part) for part in parts]
    version = ".".join(rendered[:3])
    revision = rendered[3] if len(rendered) > 3 and rendered[3] else "unknown"
    return version, revision


def _profile_path_fingerprint(profile: Path) -> str:
    """Match the addon's authenticated profile-path fingerprint."""

    normalized = os.path.normcase(os.path.realpath(str(profile)))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _validate_instance_info(
    info: object, manifest: dict[str, Any], launched_pid: int
) -> dict[str, Any]:
    if not isinstance(info, dict) or info.get("ok") is not True:
        raise InstanceValidationError("get_instance_info did not return ok=true")

    expected_profile = manifest["profile_instance_id"]
    actual_profile = info.get("profile_instance_id") or info.get("instance_id")
    if actual_profile != expected_profile:
        raise InstanceValidationError(
            f"profile mismatch: expected {expected_profile!r}, got {actual_profile!r}"
        )
    if info.get("pid") != launched_pid:
        raise InstanceValidationError(
            f"PID mismatch: launched {launched_pid}, endpoint reported {info.get('pid')!r}"
        )

    endpoint = info.get("actual_endpoint")
    if not isinstance(endpoint, dict):
        endpoint = {"host": info.get("host"), "port": info.get("port")}
    if (
        endpoint.get("host") != manifest["rpc_host"]
        or endpoint.get("port") != manifest["rpc_port"]
    ):
        raise InstanceValidationError(
            "RPC endpoint mismatch: expected "
            f"{manifest['rpc_host']}:{manifest['rpc_port']}, got "
            f"{endpoint.get('host')}:{endpoint.get('port')}"
        )

    actual_profile_path = info.get("profile_path")
    if not actual_profile_path or _normalize_path(actual_profile_path) != _normalize_path(
        manifest["profile_path"]
    ):
        raise InstanceValidationError(
            f"profile path mismatch: expected {manifest['profile_path']!r}, "
            f"got {actual_profile_path!r}"
        )

    runtime_id = info.get("addon_runtime_id")
    try:
        parsed_runtime = uuid.UUID(str(runtime_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise InstanceValidationError("addon_runtime_id is missing or invalid") from exc
    if parsed_runtime.int == 0:
        raise InstanceValidationError("addon_runtime_id must not be the nil UUID")

    addon_version = info.get("addon_version")
    addon_build_id = info.get("addon_build_id")
    freecad_version, freecad_revision = _freecad_build_identity(
        info.get("freecad_version")
    )
    process_started_at = info.get("freecad_process_started_at") or info.get(
        "addon_loaded_at"
    )
    boot_id = info.get("boot_id")
    profile_fingerprint = info.get("profile_path_fingerprint")
    protocol_version = info.get("protocol_version")
    protocol_features = info.get("protocol_features")
    if not isinstance(addon_version, str) or not addon_version:
        raise InstanceValidationError("addon_version is missing")
    if not isinstance(addon_build_id, str) or not addon_build_id:
        raise InstanceValidationError("addon_build_id is missing")
    if not freecad_version:
        raise InstanceValidationError("freecad_version is missing")
    if not isinstance(process_started_at, str) or not process_started_at:
        raise InstanceValidationError("FreeCAD process start time is missing")
    if not isinstance(boot_id, str) or not boot_id:
        raise InstanceValidationError("host boot identity is missing")
    expected_profile_fingerprint = _profile_path_fingerprint(
        Path(manifest["profile_path"])
    )
    if profile_fingerprint != expected_profile_fingerprint:
        raise InstanceValidationError("profile path fingerprint mismatch")
    if info.get("document_lease_mode") != "enforce":
        raise InstanceValidationError("isolated addon is not in document_lease_mode=enforce")
    versions = info.get("protocol_versions")
    if (
        not isinstance(versions, (list, tuple))
        or PROTOCOL_VERSION not in versions
        or protocol_version != PROTOCOL_VERSION
    ):
        raise InstanceValidationError("addon does not advertise RPC protocol v2")
    if not isinstance(protocol_features, (list, tuple)) or not all(
        isinstance(item, str) and item for item in protocol_features
    ):
        raise InstanceValidationError("RPC protocol features are missing")
    normalized_features = tuple(sorted(set(protocol_features)))
    if not REQUIRED_PROTOCOL_FEATURES.issubset(normalized_features):
        raise InstanceValidationError("addon omits required RPC protocol features")

    expectations = {
        "expected_freecad_pid": launched_pid,
        "expected_freecad_process_started_at": process_started_at,
        "expected_addon_runtime_id": str(parsed_runtime),
        "expected_boot_id": boot_id,
        "expected_protocol_version": protocol_version,
        "expected_protocol_features": list(normalized_features),
        "expected_addon_version": addon_version,
        "expected_addon_build_id": addon_build_id,
        "expected_freecad_version": freecad_version,
        "expected_freecad_revision": freecad_revision,
        "expected_profile_path_fingerprint": expected_profile_fingerprint,
    }
    for key, actual in expectations.items():
        expected = manifest.get(key)
        if expected is not None and expected != actual:
            raise InstanceValidationError(
                f"runtime manifest mismatch for {key}: expected {expected!r}, got {actual!r}"
            )
    return expectations


def _prove_authenticated_instance(
    proxy: Any,
    *,
    info: object,
    manifest: dict[str, Any],
    launched_pid: int,
    secret: bytes,
    launcher_identity: McpRuntimeIdentity | None = None,
) -> dict[str, Any]:
    """Authenticate the candidate endpoint and return only proven facts.

    ``get_instance_info`` is intentionally unauthenticated so it remains a
    compatibility/readiness probe.  Its values are used only as exact
    assertions in the signed request and response verification; callers must
    never persist them until this function succeeds.
    """

    candidate = _validate_instance_info(info, manifest, launched_pid)
    identity = launcher_identity or make_mcp_runtime_identity(
        client_build_id=LAUNCHER_BUILD_ID
    )
    try:
        request = build_handshake_request(
            secret=secret,
            mcp=identity,
            expected_profile_id=manifest["profile_instance_id"],
            expected_freecad_pid=launched_pid,
            expected_freecad_process_started_at=candidate[
                "expected_freecad_process_started_at"
            ],
            expected_addon_runtime_id=candidate["expected_addon_runtime_id"],
            expected_boot_id=candidate["expected_boot_id"],
            expected_rpc_host=manifest["rpc_host"],
            expected_rpc_port=manifest["rpc_port"],
            expected_protocol_version=candidate["expected_protocol_version"],
            expected_protocol_features=candidate[
                "expected_protocol_features"
            ],
            expected_addon_version=candidate["expected_addon_version"],
            expected_addon_build_id=candidate["expected_addon_build_id"],
            expected_freecad_version=candidate["expected_freecad_version"],
            expected_freecad_revision=candidate["expected_freecad_revision"],
            expected_profile_path_fingerprint=candidate[
                "expected_profile_path_fingerprint"
            ],
        )
        response = proxy.handshake_v2(request)
        verified = verify_handshake_response(
            response,
            secret=secret,
            expected_client_nonce=request["client_nonce"],
            expected_profile_id=manifest["profile_instance_id"],
            expected_freecad_pid=launched_pid,
            expected_addon_runtime_id=candidate["expected_addon_runtime_id"],
            expected_freecad_process_started_at=candidate[
                "expected_freecad_process_started_at"
            ],
            expected_rpc_host=manifest["rpc_host"],
            expected_rpc_port=manifest["rpc_port"],
            expected_protocol_version=candidate["expected_protocol_version"],
            expected_protocol_features=candidate[
                "expected_protocol_features"
            ],
            expected_addon_version=candidate["expected_addon_version"],
            expected_addon_build_id=candidate["expected_addon_build_id"],
            expected_freecad_version=candidate["expected_freecad_version"],
            expected_freecad_revision=candidate["expected_freecad_revision"],
            expected_boot_id=candidate["expected_boot_id"],
            expected_profile_path_fingerprint=candidate[
                "expected_profile_path_fingerprint"
            ],
        )
    except (RpcAuthError, xmlrpc.client.Error, TypeError, ValueError) as exc:
        # Authentication errors are deliberately bounded and never include the
        # profile secret or issued session credential.
        raise InstanceValidationError(
            f"authenticated RPC v2 handshake failed: {exc}"
        ) from exc

    expected_fingerprint = _profile_path_fingerprint(Path(manifest["profile_path"]))
    if verified.manifest.profile_path_fingerprint != expected_fingerprint:
        raise InstanceValidationError(
            "authenticated profile path fingerprint does not match the isolated profile"
        )

    # Populate readiness exclusively from the HMAC-authenticated manifest,
    # never from the preceding unauthenticated discovery response.
    runtime = verified.manifest
    return {
        "expected_freecad_pid": runtime.freecad_pid,
        "expected_freecad_process_started_at": runtime.freecad_process_started_at,
        "expected_addon_runtime_id": runtime.addon_runtime_id,
        "expected_boot_id": runtime.boot_id,
        "expected_protocol_version": runtime.protocol_version,
        "expected_protocol_features": list(runtime.features),
        "expected_addon_version": runtime.addon_version,
        "expected_addon_build_id": runtime.addon_build_id,
        "expected_freecad_version": runtime.freecad_version,
        "expected_freecad_revision": runtime.freecad_revision,
        "expected_profile_path_fingerprint": runtime.profile_path_fingerprint,
    }


def _load_parent_start_freecad():
    """Load FreeCADModeling/start_freecad.py for PATH/Qt helpers only."""

    parent = _repo_root().parent / "start_freecad.py"
    if not parent.is_file():
        alt = _repo_root() / ".." / "start_freecad.py"
        parent = alt.resolve() if alt.is_file() else parent
    if not parent.is_file():
        raise SystemExit(f"Parent start_freecad.py not found at {parent}")
    spec = importlib.util.spec_from_file_location("freecadmodeling_start_freecad", parent)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Cannot load {parent}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    repo = _repo_root()
    profile = repo / PROFILE_NAME
    freecad = repo / "build" / "release" / "bin" / "FreeCAD.exe"

    if not freecad.is_file():
        raise SystemExit(f"build/release FreeCAD not found: {freecad}")
    if not profile.is_dir():
        raise SystemExit(
            f"Isolated profile missing: {profile}\n"
            "Run scripts/setup_isolated_profile.py first."
        )
    for required in (profile / "Mod", profile / "temp"):
        required.mkdir(parents=True, exist_ok=True)

    manifest = _load_manifest(profile)
    host = manifest["rpc_host"]
    port = manifest["rpc_port"]
    if _normalize_path(manifest["profile_path"]) != _normalize_path(profile):
        raise SystemExit(
            "Manifest profile_path does not identify this isolated profile; "
            "run setup_isolated_profile.py again."
        )
    try:
        profile_secret = load_profile_secret(manifest["auth_secret_file"])
    except RpcAuthError as exc:
        raise SystemExit(
            f"Cannot authenticate the isolated profile: {exc.public_message}"
        ) from exc
    endpoint_reservation = _reserve_endpoint(host, port)
    try:
        helper = _load_parent_start_freecad()
        cmd, cwd, env = helper._launch_details(freecad, sys.argv[1:])
        env = dict(env)
        env["FREECAD_USER_HOME"] = str(profile)
        env["FREECAD_USER_DATA"] = str(profile)
        env["FREECAD_USER_TEMP"] = str(profile / "temp")

        print("Starting isolated FreeCAD:")
        print(f"  exe:      {freecad}")
        print(f"  profile:  {profile}")
        print(f"  manifest: {_manifest_path(profile)}")
        print(f"  RPC:      {host}:{port}")
        print("  existing default MCP instance is not contacted or stopped")

        creationflags = 0
        if sys.platform == "win32":
            creationflags = (
                subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
                | subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
            )
    except BaseException:
        endpoint_reservation.close()
        raise
    # This is the narrowest possible release-to-bind window without changing
    # FreeCAD's addon listener to inherit a pre-bound socket.
    endpoint_reservation.close()
    process = subprocess.Popen(
        cmd,
        env=env,
        cwd=cwd,
        creationflags=creationflags,
        close_fds=True,
    )
    print(f"  pid:      {process.pid}")

    # Keep launch expectations in memory.  The persistent readiness manifest
    # is not updated with candidate runtime facts until their HMAC-authenticated
    # handshake has been verified.
    launch_manifest = dict(manifest)
    launch_manifest.update(
        {
            "expected_freecad_pid": process.pid,
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

    deadline = time.monotonic() + 60.0
    launcher_identity = make_mcp_runtime_identity(client_build_id=LAUNCHER_BUILD_ID)
    proxy = xmlrpc.client.ServerProxy(
        f"http://{host}:{port}",
        allow_none=True,
        transport=_TimeoutTransport(2.0),
    )
    while time.monotonic() < deadline:
        if process.poll() is not None:
            print(
                f"ERROR: FreeCAD exited before RPC identity was proven "
                f"(code {process.returncode})",
                file=sys.stderr,
            )
            return process.returncode or 1
        try:
            info = proxy.get_instance_info()
        except (OSError, xmlrpc.client.Error):
            time.sleep(0.5)
            continue
        try:
            expectations = _prove_authenticated_instance(
                proxy,
                info=info,
                manifest=launch_manifest,
                launched_pid=process.pid,
                secret=profile_secret,
                launcher_identity=launcher_identity,
            )
        except InstanceValidationError as exc:
            print(
                f"ERROR: authenticated RPC endpoint identity validation failed: {exc}. "
                "The process was not reused or stopped.",
                file=sys.stderr,
            )
            return 1
        validated_manifest = dict(launch_manifest)
        validated_manifest.update(expectations)
        _write_manifest(profile, validated_manifest)
        print(
            f"Isolated MCP RPC identity authenticated on {host}:{port} "
            f"(pid={process.pid}, runtime={expectations['expected_addon_runtime_id']})"
        )
        return 0

    print(
        f"ERROR: FreeCAD started, but no authenticated isolated RPC appeared on "
        f"{host}:{port} within 60 seconds. The process was not stopped.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
