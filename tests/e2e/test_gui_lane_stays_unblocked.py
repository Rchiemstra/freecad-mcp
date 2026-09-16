"""Opt-in session e2e: GUI + write lanes across prune (WI-5 / §7.2–§7.3).

Not part of ``MARKER=e2e`` — marked ``session_e2e`` so the push-gate verdict
(skipped_non_xfail == 0) does not fail when these stay opt-in. Never touches
the live instance on port 9876 / ``.freecad-mcp-isolated``.

    set FREECAD_MCP_SESSION_E2E=1
    set FREECAD_MCP_ISOLATED_FREECAD=C:/path/to/build/debug/bin/FreeCAD.exe
    python -m pytest tests/e2e/test_gui_lane_stays_unblocked.py -m session_e2e -v

Soak (idle past short TTL + concurrent second runtime):

    set FREECAD_MCP_SESSION_SOAK=1
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import pytest

MCP_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = MCP_ROOT / "scripts"
PROFILE_NAME = ".freecad-mcp-e2e-session"
E2E_PORT = 9877


def _find_repo_root(mcp_root: Path) -> Path:
    for candidate in mcp_root.parents:
        if (candidate / "src" / "Main").is_dir():
            return candidate
    return mcp_root


REPO_ROOT = _find_repo_root(MCP_ROOT)
DEFAULT_PROFILE = ".freecad-mcp-isolated"
SHORT_TTL_SECONDS = 2.0
# Far-future client expiry so ensure_session_fresh does not hide the reactive
# INVALID_SESSION path that §7.2 / §4.3 require.
FAR_FUTURE_EXPIRY = "2099-01-01T00:00:00Z"
LAUNCH_TIMEOUT_SECONDS = 90.0
CHILD_STOP_TIMEOUT_SECONDS = 30.0


class SessionCleanupSafetyError(RuntimeError):
    """Cleanup stopped because the target child or profile was not proven."""


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip() not in {"", "0", "false", "False"}


pytestmark = [
    pytest.mark.session_e2e,
    pytest.mark.skipif(
        not _truthy("FREECAD_MCP_SESSION_E2E"),
        reason="Set FREECAD_MCP_SESSION_E2E=1 to run throwaway-profile session e2e",
    ),
]


def _endpoint_accepts(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.25):
            return True
    except OSError:
        return False


def _path_is_redirected(profile: Path) -> bool:
    """Detect symlinks, Windows junctions, and other directory reparse points."""

    if profile.is_symlink():
        return True
    is_junction = getattr(profile, "is_junction", None)
    if callable(is_junction) and is_junction():
        return True
    if os.name == "nt":
        try:
            attributes = int(getattr(os.lstat(profile), "st_file_attributes", 0))
        except FileNotFoundError:
            return False
        return bool(
            attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
        )
    return False


def _assert_throwaway_profile_isolated(profile: Path) -> None:
    """Fail explicitly unless *profile* is the one fixed disposable directory."""

    expected = (REPO_ROOT / PROFILE_NAME).resolve()
    default = (REPO_ROOT / DEFAULT_PROFILE).resolve()
    if _path_is_redirected(profile):
        raise SessionCleanupSafetyError(
            f"Refusing redirected throwaway profile: {profile}"
        )
    resolved = profile.resolve()
    if resolved != expected or resolved == default:
        raise SessionCleanupSafetyError(
            f"Refusing cleanup outside fixed throwaway profile: {resolved}"
        )
    live_manifest = REPO_ROOT / DEFAULT_PROFILE / "instance-manifest.json"
    if live_manifest.is_file():
        try:
            live_value = json.loads(live_manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise SessionCleanupSafetyError(
                f"Cannot verify default-profile endpoint isolation: {exc}"
            ) from exc
        if not isinstance(live_value, dict) or live_value.get("rpc_port") == E2E_PORT:
            raise SessionCleanupSafetyError(
                "Throwaway endpoint overlaps the default MCP profile"
            )


def _load_json_object(path: Path, *, label: str) -> dict | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SessionCleanupSafetyError(f"Cannot read {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SessionCleanupSafetyError(f"{label} must contain a JSON object: {path}")
    return value


def _positive_pid(value: object, *, label: str, allow_missing: bool = False) -> int | None:
    if value is None and allow_missing:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise SessionCleanupSafetyError(f"{label} must be a positive integer PID")
    return value


def _load_launch_manifest(manifest_path: Path, profile: Path) -> dict:
    manifest = _load_json_object(manifest_path, label="readiness manifest")
    if manifest is None:
        raise SessionCleanupSafetyError(f"Readiness manifest is missing: {manifest_path}")
    if manifest.get("rpc_host") != "127.0.0.1" or manifest.get("rpc_port") != E2E_PORT:
        raise SessionCleanupSafetyError("Readiness manifest endpoint is not isolated")
    if Path(str(manifest.get("profile_path") or "")).resolve() != profile.resolve():
        raise SessionCleanupSafetyError("Readiness manifest profile path mismatch")
    _positive_pid(manifest.get("expected_freecad_pid"), label="readiness manifest")
    for field in (
        "profile_instance_id",
        "expected_freecad_process_started_at",
        "expected_addon_runtime_id",
        "expected_boot_id",
        "expected_profile_path_fingerprint",
    ):
        if not isinstance(manifest.get(field), str) or not manifest[field]:
            raise SessionCleanupSafetyError(
                f"Readiness manifest is missing authenticated field {field}"
            )
    return manifest


def _assert_authenticated_child_identity(
    *,
    connection,
    verified,
    launch_manifest: dict,
    profile: Path,
) -> None:
    runtime = verified.manifest
    expected_pid = _positive_pid(
        launch_manifest.get("expected_freecad_pid"),
        label="authenticated child identity",
    )
    checks = {
        "PID": (runtime.freecad_pid, expected_pid),
        "profile identity": (runtime.profile_id, launch_manifest.get("profile_instance_id")),
        "RPC host": (runtime.rpc_host, "127.0.0.1"),
        "RPC port": (runtime.rpc_port, E2E_PORT),
    }
    optional_checks = {
        "runtime identity": (
            runtime.addon_runtime_id,
            launch_manifest.get("expected_addon_runtime_id"),
        ),
        "process start": (
            runtime.freecad_process_started_at,
            launch_manifest.get("expected_freecad_process_started_at"),
        ),
        "boot identity": (runtime.boot_id, launch_manifest.get("expected_boot_id")),
        "profile fingerprint": (
            runtime.profile_path_fingerprint,
            launch_manifest.get("expected_profile_path_fingerprint"),
        ),
    }
    for label, (actual, expected_value) in {**checks, **optional_checks}.items():
        if expected_value not in (None, "") and actual != expected_value:
            raise SessionCleanupSafetyError(
                f"Authenticated throwaway child {label} mismatch"
            )

    info = connection.get_instance_info()
    if info.get("pid") != runtime.freecad_pid:
        raise SessionCleanupSafetyError("Runtime discovery PID changed after authentication")
    if info.get("addon_runtime_id") != runtime.addon_runtime_id:
        raise SessionCleanupSafetyError(
            "Runtime discovery identity changed after authentication"
        )
    if (info.get("profile_instance_id") or info.get("instance_id")) != runtime.profile_id:
        raise SessionCleanupSafetyError("Runtime discovery profile identity mismatch")
    if Path(str(info.get("profile_path") or "")).resolve() != profile.resolve():
        raise SessionCleanupSafetyError("Authenticated runtime profile path mismatch")
    endpoint = info.get("actual_endpoint")
    if not isinstance(endpoint, dict):
        endpoint = {"host": info.get("host"), "port": info.get("port")}
    if endpoint.get("host") != "127.0.0.1" or endpoint.get("port") != E2E_PORT:
        raise SessionCleanupSafetyError("Authenticated runtime endpoint mismatch")


def _launcher_output(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[-4000:]
    except OSError:
        return ""


def _remove_throwaway_profile(profile: Path) -> None:
    _assert_throwaway_profile_isolated(profile)
    if not profile.exists():
        return
    shutil.rmtree(profile)
    if profile.exists():
        raise SessionCleanupSafetyError(
            f"Throwaway profile deletion could not be verified: {profile}"
        )


_LIFECYCLE_IDENTITY_FIELDS = (
    "profile_instance_id",
    "expected_freecad_pid",
    "expected_freecad_process_started_at",
    "expected_addon_runtime_id",
    "expected_boot_id",
    "expected_profile_path_fingerprint",
)


def _same_launch_identity(current: dict, expected: dict) -> bool:
    return all(current.get(field) == expected.get(field) for field in _LIFECYCLE_IDENTITY_FIELDS)


def _cleanup_throwaway_session(
    profile: Path,
    manifest_path: Path,
    *,
    supervisor=None,
    launch_manifest: dict | None = None,
) -> None:
    """Stop only through the still-live supervisor that created the child."""

    if supervisor is None:
        _assert_throwaway_profile_isolated(profile)
        if not profile.exists():
            return
        raise SessionCleanupSafetyError(
            "Throwaway profile has no retained launch supervisor; no PID-based "
            "cleanup was attempted and the profile was preserved"
        )
    try:
        supervisor_exit = supervisor.poll()
    except Exception as exc:
        raise SessionCleanupSafetyError(
            "Throwaway supervisor state could not be verified; its child and profile "
            f"were preserved: {exc}"
        ) from exc
    if supervisor_exit is not None:
        raise SessionCleanupSafetyError(
            "Throwaway supervisor exited before identity-bound cleanup; no fallback "
            "PID cleanup was attempted and the profile was preserved"
        )
    cleanup_proven = False
    proof_error: Exception | None = None
    connection = None
    try:
        _assert_throwaway_profile_isolated(profile)
        if not isinstance(launch_manifest, dict):
            raise SessionCleanupSafetyError(
                "no authenticated launch identity was available"
            )
        current_manifest = _load_launch_manifest(manifest_path, profile)
        if not _same_launch_identity(current_manifest, launch_manifest):
            raise SessionCleanupSafetyError(
                "throwaway readiness identity changed after launch"
            )
        connection, verified, _ = _handshake_connection(manifest_path, E2E_PORT)
        _assert_authenticated_child_identity(
            connection=connection,
            verified=verified,
            launch_manifest=launch_manifest,
            profile=profile,
        )
        cleanup_proven = True
    except Exception as exc:
        proof_error = exc
    finally:
        if connection is not None:
            with contextlib.suppress(Exception):
                connection.disconnect()

    # The retained Popen/control pipe is creation-time authority over the exact
    # supervisor. Always stop it, even when identity proof failed. Manifest and
    # HMAC evidence gate profile deletion only—not owned-process termination.
    _stop_retained_supervisor(supervisor)
    if not profile.exists():
        return
    if not cleanup_proven:
        raise SessionCleanupSafetyError(
            "The exact retained supervisor was stopped, but cleanup identity could "
            f"not be proven; the profile was preserved for inspection: {proof_error}"
        ) from proof_error

    deadline = time.monotonic() + CHILD_STOP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if not _endpoint_accepts("127.0.0.1", E2E_PORT):
            _remove_throwaway_profile(profile)
            return
        time.sleep(0.25)
    raise SessionCleanupSafetyError(
        "The retained supervisor stopped but the throwaway endpoint remained "
        "occupied; the profile was preserved"
    )


def _command_retained_supervisor(supervisor) -> None:
    control = getattr(supervisor, "stdin", None)
    if control is None or getattr(control, "closed", False):
        raise SessionCleanupSafetyError(
            "Throwaway supervisor control pipe is unavailable; the child and "
            "profile were preserved"
        )
    # STOP is consumed only by the retained launcher. FreeCAD receives DEVNULL
    # as stdin and cannot steal or forge this creation-owned command channel.
    control.write("STOP\n")
    control.flush()


def _wait_retained_supervisor(supervisor) -> None:
    try:
        supervisor_exit = supervisor.wait(timeout=CHILD_STOP_TIMEOUT_SECONDS)
    except Exception as exc:
        raise SessionCleanupSafetyError(
            "Throwaway supervisor did not confirm exact-tree shutdown; no fallback "
            f"PID cleanup was attempted and the profile was preserved: {exc}"
        ) from exc
    if supervisor_exit != 0:
        raise SessionCleanupSafetyError(
            f"Throwaway supervisor reported shutdown failure {supervisor_exit}; "
            "the profile was preserved"
        )


def _stop_retained_supervisor(supervisor) -> None:
    try:
        _command_retained_supervisor(supervisor)
        _wait_retained_supervisor(supervisor)
    except SessionCleanupSafetyError:
        raise
    except Exception as exc:
        raise SessionCleanupSafetyError(
            "The exact retained supervisor could not be stopped after interrupted "
            f"readiness; no fallback PID cleanup was attempted: {exc}"
        ) from exc


def _wait_for_supervised_readiness(
    supervisor,
    manifest_path: Path,
    profile: Path,
    launcher_log: Path,
) -> dict:
    """Wait for launcher-published identity without waiting for launcher exit."""

    deadline = time.monotonic() + LAUNCH_TIMEOUT_SECONDS
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        returncode = supervisor.poll()
        if returncode is not None:
            raise SessionCleanupSafetyError(
                f"Throwaway supervisor exited before readiness ({returncode}): "
                f"{_launcher_output(launcher_log)}"
            )
        try:
            launch_manifest = _load_launch_manifest(manifest_path, profile)
        except SessionCleanupSafetyError as exc:
            last_error = exc
            time.sleep(0.25)
            continue
        try:
            startup_conn, startup_verified, _ = _handshake_connection(
                manifest_path, E2E_PORT
            )
        except Exception as exc:
            last_error = exc
            time.sleep(0.25)
            continue
        try:
            _assert_authenticated_child_identity(
                connection=startup_conn,
                verified=startup_verified,
                launch_manifest=launch_manifest,
                profile=profile,
            )
        finally:
            startup_conn.disconnect()
        return launch_manifest
    raise SessionCleanupSafetyError(
        "Throwaway supervisor did not publish authenticated readiness within "
        f"{LAUNCH_TIMEOUT_SECONDS:g}s ({last_error}); "
        f"launcher output: {_launcher_output(launcher_log)}"
    )


@contextlib.contextmanager
def _throwaway_cleanup_scope(profile: Path, manifest_path: Path, ownership: dict):
    """Register cleanup before any setup step can fail prior to fixture yield."""

    try:
        yield ownership
    finally:
        _cleanup_throwaway_session(
            profile,
            manifest_path,
            supervisor=ownership.get("supervisor"),
            launch_manifest=ownership.get("launch_manifest"),
        )


@pytest.fixture(scope="module")
def throwaway_profile():
    profile = REPO_ROOT / PROFILE_NAME
    _assert_throwaway_profile_isolated(profile)
    manifest_path = profile / "instance-manifest.json"
    if profile.exists():
        raise SessionCleanupSafetyError(
            "Pre-existing throwaway profile has no retained supervisor; refusing "
            "retrospective PID cleanup. Remove it only after independently proving "
            "that its prior test child is stopped."
        )

    env = os.environ.copy()
    # Pin both scripts to the exact throwaway path even if the caller normally
    # uses FREECAD_MCP_PROFILE_DIR for a persistent/default profile.
    env["FREECAD_MCP_PROFILE_DIR"] = str(profile.resolve())
    try:
        setup = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "setup_isolated_profile.py"),
                "--port",
                str(E2E_PORT),
                "--profile-name",
                PROFILE_NAME,
            ],
            cwd=str(MCP_ROOT),
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        if setup.returncode != 0:
            pytest.fail(
                f"setup_isolated_profile failed: {setup.stderr or setup.stdout}"
            )
    except BaseException:
        # Preexistence was rejected above and no child has been spawned yet.
        if profile.exists():
            _remove_throwaway_profile(profile)
        raise

    try:
        _assert_throwaway_profile_isolated(profile)
        debug_dir = profile / "debug_logs"
        debug_dir.mkdir(parents=True, exist_ok=True)
        launcher_log = debug_dir / "launcher.log"
        env["FREECAD_MCP_DEBUG_LOG_DIR"] = str(debug_dir)
        env["FREECAD_MCP_SESSION_TTL_SECONDS"] = str(SHORT_TTL_SECONDS)
    except BaseException:
        # Setup succeeded, but no child has been spawned yet.
        if profile.exists():
            _remove_throwaway_profile(profile)
        raise

    supervisor = None
    ownership = {"supervisor": None, "launch_manifest": None}
    try:
        with _throwaway_cleanup_scope(profile, manifest_path, ownership):
            with launcher_log.open("w", encoding="utf-8") as output:
                supervisor = subprocess.Popen(
                    [
                        sys.executable,
                        str(SCRIPTS / "start_freecad_isolated.py"),
                        "--supervise",
                        "--profile-name",
                        PROFILE_NAME,
                    ],
                    cwd=str(MCP_ROOT),
                    stdin=subprocess.PIPE,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    text=True,
                    env=env,
                    close_fds=True,
                )
                # Transfer ownership immediately while still inside every
                # surrounding context that could fail during unwinding.
                ownership["supervisor"] = supervisor

            launch_manifest = _wait_for_supervised_readiness(
                supervisor,
                manifest_path,
                profile,
                launcher_log,
            )
            ownership["launch_manifest"] = launch_manifest
            child_pid = launch_manifest["expected_freecad_pid"]

            yield {
                "profile": profile,
                "port": E2E_PORT,
                "child_pid": child_pid,
                "debug_dir": debug_dir,
                "manifest": manifest_path,
                "launch_manifest": launch_manifest,
                "ttl": SHORT_TTL_SECONDS,
            }
    except BaseException:
        if supervisor is not None and ownership.get("supervisor") is None:
            # Covers interruption between Popen returning and the immediately
            # following ownership assignment. The local Popen is still the
            # exact creation-owned supervisor, so stop it through its pipe.
            _cleanup_throwaway_session(
                profile,
                manifest_path,
                supervisor=supervisor,
                launch_manifest=None,
            )
        elif supervisor is None and profile.exists():
            # No child ownership was transferred. This remains a known-new,
            # child-free profile and is safe to remove after path revalidation.
            _remove_throwaway_profile(profile)
        raise


def _handshake_connection(
    manifest_path: Path,
    port: int,
    *,
    runtime_id: str | None = None,
    client_expires_at: str | None = None,
):
    """Authenticate one MCP runtime; refresher re-handshakes in-place."""

    from freecad_mcp.freecad_client import FreeCADConnection
    from freecad_mcp.freecad_client_ops.connection_methods.connection_headers_ops import (
        configure_rpc_session,
        configure_session_refresher,
    )
    from freecad_mcp.rpc_auth import (
        build_handshake_request_from_manifest,
        load_profile_secret,
        make_mcp_runtime_identity,
        make_runtime_manifest,
        verify_handshake_response_from_manifest,
    )
    from freecad_mcp.rpc_session import RpcAuthenticationSession

    conn = FreeCADConnection(host="127.0.0.1", port=port)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        info = conn.get_instance_info()
        secret = load_profile_secret(manifest["auth_secret_file"])
        runtime = make_runtime_manifest(
            profile_id=manifest["profile_instance_id"],
            addon_runtime_id=str(info.get("addon_runtime_id") or uuid.uuid4()),
            freecad_pid=int(info.get("pid") or 1),
            freecad_process_started_at=str(
                info.get("freecad_process_started_at")
                or info.get("process_started_at")
                or "2026-01-01T00:00:00Z"
            ),
            boot_id=str(info.get("boot_id") or "boot"),
            rpc_host=manifest["rpc_host"],
            rpc_port=port,
            freecad_version=str(info.get("freecad_version") or "0"),
            freecad_revision=str(info.get("freecad_revision") or "0"),
            addon_version=str(info.get("addon_version") or "0"),
            addon_build_id=str(info.get("addon_build_id") or "0"),
            profile_path_fingerprint=str(
                info.get("profile_path_fingerprint") or "sha256:0"
            ),
        )
        mcp_runtime_id = runtime_id or str(uuid.uuid4())

        def _perform_handshake() -> object:
            mcp = make_mcp_runtime_identity(
                runtime_id=mcp_runtime_id,
                pid=os.getpid(),
                process_started_at="2026-01-01T00:00:00Z",
                hostname="e2e-host",
                client_build_id="e2e",
            )
            request = build_handshake_request_from_manifest(
                secret=secret, mcp=mcp, manifest=runtime
            )
            response = conn.invoke_rpc("handshake_v2", request, control=True)
            return verify_handshake_response_from_manifest(
                response,
                secret=secret,
                expected_client_nonce=request["client_nonce"],
                manifest=runtime,
            )

        verified = _perform_handshake()
        session = RpcAuthenticationSession()
        expires_at = client_expires_at or verified.session_expires_at
        session.mark_connected(
            verified.session_token,
            session_id=verified.session_id,
            expires_at=expires_at,
        )
        configure_rpc_session(conn, session)

        def refresher() -> None:
            refreshed = _perform_handshake()
            # Keep far-future client expiry when testing reactive prune recovery so
            # the next call does not flip back to proactive-only behaviour mid-test.
            next_expiry = client_expires_at or refreshed.session_expires_at
            session.mark_connected(
                refreshed.session_token,
                session_id=refreshed.session_id,
                expires_at=next_expiry,
            )

        configure_session_refresher(conn, refresher)
        return conn, verified, mcp_runtime_id
    except BaseException:
        with contextlib.suppress(Exception):
            conn.disconnect()
        raise


def _assert_no_session_refusal(payload: object) -> None:
    text = str(payload)
    assert "INVALID_SESSION" not in text
    assert "SESSION_EXPIRED" not in text
    assert "SESSION_REVOKED" not in text
    assert "SESSION_BINDING_MISMATCH" not in text
    if isinstance(payload, dict):
        assert payload.get("error_code") not in {
            "INVALID_SESSION",
            "SESSION_EXPIRED",
            "SESSION_REVOKED",
            "SESSION_BINDING_MISMATCH",
        }
        assert payload.get("success") is not False


def _assert_v2_success(payload: object) -> dict:
    assert isinstance(payload, dict), payload
    assert payload.get("success") is True, payload
    assert isinstance(payload.get("request_id"), str) and payload["request_id"], payload
    assert (
        isinstance(payload.get("addon_runtime_id"), str)
        and payload["addon_runtime_id"]
    ), payload
    return payload


def _assert_clean_readiness(payload: object, doc_name: str) -> None:
    assert isinstance(payload, dict), payload
    assert payload.get("success") is True, payload
    assert payload.get("ready") is True, payload
    documents = payload.get("documents")
    assert isinstance(documents, list) and len(documents) == 1, payload
    document = documents[0]
    assert document.get("document") == doc_name, payload
    assert document.get("ready") is True, payload
    assert document.get("pending_transaction") is False, payload
    assert document.get("booked_transaction_id") == 0, payload
    assert document.get("transaction_locked") is False, payload
    assert document.get("must_execute") is False, payload
    assert document.get("recomputing") is False, payload
    assert document.get("collaboration_blocked") is False, payload
    assert document.get("commit_barrier") is False, payload
    assert document.get("collaboration_poisoned") is False, payload
    assert document.get("quarantined") is False, payload


def test_gui_and_write_recover_after_ttl_prune(throwaway_profile):
    """§7.2: reactive recovery after short-TTL + second-runtime prune + WI-4 logs."""

    port = throwaway_profile["port"]
    manifest = throwaway_profile["manifest"]
    debug_dir = throwaway_profile["debug_dir"]
    ttl = float(throwaway_profile["ttl"])

    # Far-future client expiry disables proactive refresh so the stale token is
    # actually sent after prune (reactive INVALID_SESSION path).
    conn_a, _verified_a, _runtime_a = _handshake_connection(
        manifest, port, client_expires_at=FAR_FUTURE_EXPIRY
    )
    created_documents: list[str] = []
    try:
        gui = conn_a.get_gui_state()
        assert isinstance(gui, dict)
        _assert_no_session_refusal(gui)

        created = conn_a.create_document(f"E2ESession{uuid.uuid4().hex[:8]}")
        assert isinstance(created, dict)
        assert created.get("success") is True, created
        doc_name = created.get("document_name")
        assert isinstance(doc_name, str) and doc_name, created
        created_documents.append(doc_name)

        # Idle past server TTL, then B handshakes and prunes A's record.
        time.sleep(ttl + 0.5)
        conn_b, _verified_b, _runtime_b = _handshake_connection(manifest, port)
        conn_b.disconnect()

        gui_after = conn_a.get_gui_state()
        assert isinstance(gui_after, dict)
        _assert_no_session_refusal(gui_after)

        created_after = conn_a.create_document(f"E2EAfter{uuid.uuid4().hex[:8]}")
        assert isinstance(created_after, dict)
        assert created_after.get("success") is True, created_after
        _assert_no_session_refusal(created_after)
        created_after_name = created_after.get("document_name")
        assert isinstance(created_after_name, str) and created_after_name
        created_documents.append(created_after_name)

        activated = conn_a.activate_document(doc_name)
        assert isinstance(activated, dict)
        _assert_no_session_refusal(activated)
    finally:
        for created_name in reversed(created_documents):
            with contextlib.suppress(Exception):
                conn_a._invoke_mutation_v2(
                    "close_document",
                    {"doc_name": created_name},
                    document_names=(created_name,),
                    operation_name="Close session recovery E2E document",
                )
        conn_a.disconnect()

    log_text = ""
    for path in debug_dir.glob("*.jsonl"):
        log_text += path.read_text(encoding="utf-8")
    assert debug_dir.is_dir()
    assert DEFAULT_PROFILE not in str(debug_dir)
    assert "auth_gate_refused" in log_text, (
        f"expected WI-4 auth_gate_refused after prune; got {log_text[:800]!r}"
    )
    assert "INVALID_SESSION" in log_text or "SESSION_EXPIRED" in log_text, (
        f"expected session protocol code in debug_logs; got {log_text[:800]!r}"
    )


def test_failed_feature_does_not_poison_authenticated_write_lane(throwaway_profile):
    """A failed strict Pad must not block another document's feature history."""

    port = throwaway_profile["port"]
    manifest = throwaway_profile["manifest"]
    conn, _verified, _runtime_id = _handshake_connection(manifest, port)
    documents: list[str] = []
    try:
        requested_a = f"BadProfile{uuid.uuid4().hex[:8]}"
        created_a = conn.create_document(requested_a)
        assert created_a.get("success") is True, created_a
        doc_a = str(created_a.get("document_name") or requested_a)
        documents.append(doc_a)

        assert conn.body_create(doc_a, "Body").get("success") is True
        assert conn.sketch_create(
            doc_a,
            "OpenProfile",
            body_name="Body",
            attach_to="XY_Plane",
        ).get("success") is True
        assert conn.sketch_add_geometry(
            doc_a,
            "OpenProfile",
            [
                {
                    "type": "line",
                    "start": {"x": 0.0, "y": 0.0},
                    "end": {"x": 10.0, "y": 0.0},
                }
            ],
        ).get("success") is True

        failed_pad = conn.pad_feature(
            doc_a,
            "OpenProfile",
            "BadPad",
            4.0,
            body_name="Body",
            strict=True,
        )
        assert failed_pad.get("success") is False, failed_pad
        assert failed_pad.get("error") == "Sketch profile is not pad-ready", failed_pad
        diagnostics = failed_pad.get("diagnostics")
        assert isinstance(diagnostics, dict) and diagnostics.get("is_closed") is not True
        assert isinstance(failed_pad.get("request_id"), str) and failed_pad["request_id"]
        assert (
            isinstance(failed_pad.get("addon_runtime_id"), str)
            and failed_pad["addon_runtime_id"]
        )
        assert conn.get_object(doc_a, "BadPad") is None
        _assert_clean_readiness(conn.get_mutation_readiness(doc_a), doc_a)

        requested_b = f"GoodProfile{uuid.uuid4().hex[:8]}"
        created_b = conn.create_document(requested_b)
        assert created_b.get("success") is True, created_b
        doc_b = str(created_b.get("document_name") or requested_b)
        documents.append(doc_b)

        assert conn.body_create(doc_b, "Body").get("success") is True
        assert conn.sketch_create(
            doc_b,
            "Outer",
            body_name="Body",
            attach_to="XY_Plane",
        ).get("success") is True
        assert conn.sketch_add_geometry(
            doc_b,
            "Outer",
            [{"type": "circle", "center": {"x": 0.0, "y": 0.0}, "radius": 6.0}],
        ).get("success") is True
        _assert_v2_success(
            conn.pad_feature(
                doc_b,
                "Outer",
                "Pad",
                4.0,
                body_name="Body",
                strict=True,
            )
        )

        assert conn.sketch_create(
            doc_b,
            "Inner",
            body_name="Body",
            attach_to="XY_Plane",
        ).get("success") is True
        assert conn.sketch_add_geometry(
            doc_b,
            "Inner",
            [{"type": "circle", "center": {"x": 0.0, "y": 0.0}, "radius": 2.0}],
        ).get("success") is True
        _assert_v2_success(
            conn.pocket_feature(
                doc_b,
                "Inner",
                "Pocket",
                4.0,
                body_name="Body",
                reversed_dir=True,
                strict=True,
            )
        )
        assert conn.get_object(doc_b, "Pocket") is not None

        _assert_v2_success(conn.undo(doc_b))
        assert conn.get_object(doc_b, "Pocket") is None
        assert conn.get_object(doc_b, "Pad") is not None
        _assert_clean_readiness(conn.get_mutation_readiness(doc_b), doc_b)

        _assert_v2_success(conn.redo(doc_b))
        assert conn.get_object(doc_b, "Pocket") is not None
        _assert_clean_readiness(conn.get_mutation_readiness(doc_a), doc_a)
        _assert_clean_readiness(conn.get_mutation_readiness(doc_b), doc_b)
    finally:
        for doc_name in reversed(documents):
            with contextlib.suppress(Exception):
                closed = conn._invoke_mutation_v2(
                    "close_document",
                    {"doc_name": doc_name},
                    document_names=(doc_name,),
                    operation_name="Close session E2E document",
                )
                if closed is None:
                    conn.invoke_rpc("close_document", doc_name)
        conn.disconnect()


@pytest.mark.skipif(
    not _truthy("FREECAD_MCP_SESSION_SOAK"),
    reason="Set FREECAD_MCP_SESSION_SOAK=1 for multi-cycle soak",
)
def test_session_soak_zero_refusals(throwaway_profile):
    """§7.3: reuse a session across idle-past-TTL cycles with a second runtime."""

    port = throwaway_profile["port"]
    manifest = throwaway_profile["manifest"]
    ttl = float(throwaway_profile["ttl"])
    cycles = int(os.environ.get("FREECAD_MCP_SESSION_SOAK_CYCLES", "3"))
    stop = threading.Event()
    errors: list[BaseException] = []

    def second_runtime():
        try:
            while not stop.wait(ttl / 2):
                other, _, _ = _handshake_connection(manifest, port)
                other.disconnect()
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    worker = threading.Thread(target=second_runtime, daemon=True)
    worker.start()
    refusals = 0
    try:
        conn, _, _ = _handshake_connection(
            manifest, port, client_expires_at=FAR_FUTURE_EXPIRY
        )
        try:
            for index in range(cycles):
                time.sleep(ttl + 0.25)
                try:
                    gui = conn.get_gui_state()
                    _assert_no_session_refusal(gui)
                    created = conn.create_document(f"Soak{index}{uuid.uuid4().hex[:6]}")
                    assert created.get("success") is True, created
                    _assert_no_session_refusal(created)
                except AssertionError:
                    refusals += 1
                    raise
        finally:
            conn.disconnect()
    finally:
        stop.set()
        worker.join(timeout=30)
    assert not errors, errors
    assert refusals == 0, f"session refusals during soak: {refusals}"
