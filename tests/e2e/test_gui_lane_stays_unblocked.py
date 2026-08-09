"""E2E: GUI + write lanes stay unblocked across session prune (WI-5 / §7.2–§7.3).

Opt-in only — never touches the live instance on port 9876 /
``.freecad-mcp-isolated``.

    set FREECAD_MCP_SESSION_E2E=1
    python -m pytest tests/e2e/test_gui_lane_stays_unblocked.py -m e2e -v

Soak (idle past short TTL + concurrent second runtime):

    set FREECAD_MCP_SESSION_SOAK=1
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
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
REPO_ROOT = MCP_ROOT.parents[2]
DEFAULT_PROFILE = ".freecad-mcp-isolated"
SHORT_TTL_SECONDS = 2.0
# Far-future client expiry so ensure_session_fresh does not hide the reactive
# INVALID_SESSION path that §7.2 / §4.3 require.
FAR_FUTURE_EXPIRY = "2099-01-01T00:00:00Z"


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip() not in {"", "0", "false", "False"}


pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not _truthy("FREECAD_MCP_SESSION_E2E"),
        reason="Set FREECAD_MCP_SESSION_E2E=1 to run throwaway-profile session e2e",
    ),
]


@pytest.fixture(scope="module")
def throwaway_profile():
    profile = REPO_ROOT / PROFILE_NAME
    if profile.exists():
        shutil.rmtree(profile, ignore_errors=True)

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
    )
    if setup.returncode != 0:
        pytest.skip(f"setup_isolated_profile failed: {setup.stderr or setup.stdout}")

    assert profile.resolve() != (REPO_ROOT / DEFAULT_PROFILE).resolve()
    live_manifest = REPO_ROOT / DEFAULT_PROFILE / "instance-manifest.json"
    if live_manifest.is_file():
        live_port = json.loads(live_manifest.read_text(encoding="utf-8")).get("rpc_port")
        assert live_port != E2E_PORT

    debug_dir = profile / "debug_logs"
    debug_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["FREECAD_MCP_DEBUG_LOG_DIR"] = str(debug_dir)
    env["FREECAD_MCP_SESSION_TTL_SECONDS"] = str(SHORT_TTL_SECONDS)

    proc = subprocess.Popen(
        [
            sys.executable,
            str(SCRIPTS / "start_freecad_isolated.py"),
            "--profile-name",
            PROFILE_NAME,
        ],
        cwd=str(MCP_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )
    from freecad_mcp.freecad_client import FreeCADConnection

    deadline = time.time() + 90
    ready = False
    while time.time() < deadline:
        if proc.poll() is not None:
            out = proc.stdout.read() if proc.stdout else ""
            shutil.rmtree(profile, ignore_errors=True)
            pytest.skip(f"throwaway FreeCAD exited early: {out[-2000:]}")
        try:
            conn = FreeCADConnection(host="127.0.0.1", port=E2E_PORT)
            if conn.ping():
                ready = True
                conn.disconnect()
                break
            conn.disconnect()
        except Exception:
            time.sleep(1.0)
    if not ready:
        with contextlib.suppress(Exception):
            proc.terminate()
            proc.wait(timeout=15)
        shutil.rmtree(profile, ignore_errors=True)
        pytest.skip("throwaway FreeCAD RPC did not become ready")

    yield {
        "profile": profile,
        "port": E2E_PORT,
        "proc": proc,
        "debug_dir": debug_dir,
        "manifest": profile / "instance-manifest.json",
        "ttl": SHORT_TTL_SECONDS,
    }

    with contextlib.suppress(Exception):
        proc.terminate()
        proc.wait(timeout=30)
    shutil.rmtree(profile, ignore_errors=True)


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

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    conn = FreeCADConnection(host="127.0.0.1", port=port)
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
    try:
        gui = conn_a.get_gui_state()
        assert isinstance(gui, dict)
        _assert_no_session_refusal(gui)

        created = conn_a.create_document(f"E2ESession{uuid.uuid4().hex[:8]}")
        assert isinstance(created, dict)
        assert created.get("success") is True, created
        doc_name = created.get("document_name")
        assert isinstance(doc_name, str) and doc_name, created

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

        activated = conn_a.activate_document(doc_name)
        assert isinstance(activated, dict)
        _assert_no_session_refusal(activated)
    finally:
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
