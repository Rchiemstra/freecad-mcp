"""Session-recovery contract tests (WI-0/WI-3).

Covers the reported bug: handshake → expire → prune via a second MCP
handshake → authenticated call must re-handshake; the caller must never see
INVALID_SESSION. Also locks classification of every authenticate() code and
both refusal shapes.
"""

from __future__ import annotations

import ast
import re
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from addon.FreeCADMCP.rpc_server.lease_protocol import (
    LeaseProtocolError,
    McpRuntimeIdentity,
    SessionManager,
    build_handshake_request,
    make_runtime_manifest,
    verify_handshake_response,
)
from addon.FreeCADMCP.rpc_server.methods.dispatch_helpers_ops.dispatch_core_enforcement_auth import (
    AUTHENTICATED_METHODS,
    GUI_AUTHENTICATED_METHODS,
)
from freecad_mcp._shared.protocol.json_rpc_client import JsonRpcRemoteError
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.freecad_client_ops.connection_methods.connection_headers_ops import (
    configure_rpc_session,
    configure_session_refresher,
)
from freecad_mcp.generated.capabilities.connection_methods import (
    connection_invoke_v2_helpers as helpers,
)
from freecad_mcp.generated.capabilities.connection_methods import (
    connection_invoke_v2_ops,
)
from freecad_mcp.rpc_session import RpcAuthenticationContext, RpcAuthenticationSession

pytestmark = pytest.mark.unit

SECRET = b"p" * 32
NOW = "2026-07-22T10:00:00.000000Z"
MCP_A = "3201517e-5664-4ee0-9168-81b46f29f0e0"
MCP_B = "bd2463a0-20c0-48bc-98db-435e272cfe48"

_REPO = Path(__file__).resolve().parents[1]
_SESSION_MANAGER = (
    _REPO
    / "addon"
    / "FreeCADMCP"
    / "_shared"
    / "protocol"
    / "session_manager.py"
)


def _manifest():
    return make_runtime_manifest(
        profile_id="isolated-profile-a",
        addon_runtime_id="8c897b64-0f04-4e09-9f80-2873d4527b7f",
        freecad_pid=4321,
        freecad_process_started_at=NOW,
        boot_id="boot-a",
        rpc_host="127.0.0.1",
        rpc_port=9876,
        freecad_version="1.0.0",
        freecad_revision="abc123",
        addon_version="0.1.20",
        addon_build_id="build-a",
        profile_path_fingerprint="sha256:0123456789abcdef",
    )


def _mcp(runtime_id: str = MCP_A):
    return McpRuntimeIdentity(
        runtime_id=runtime_id,
        pid=8765,
        process_started_at=NOW,
        hostname="test-host",
        client_build_id="client-build-a",
    )


def _handshake_request(manifest, *, mcp_runtime_id: str):
    return build_handshake_request(
        secret=SECRET,
        mcp=_mcp(mcp_runtime_id),
        expected_profile_id=manifest.profile_id,
        expected_freecad_pid=manifest.freecad_pid,
        expected_freecad_process_started_at=manifest.freecad_process_started_at,
        expected_addon_runtime_id=manifest.addon_runtime_id,
        expected_boot_id=manifest.boot_id,
        expected_rpc_host=manifest.rpc_host,
        expected_rpc_port=manifest.rpc_port,
        expected_protocol_version=manifest.protocol_version,
        expected_protocol_features=manifest.features,
        expected_addon_version=manifest.addon_version,
        expected_addon_build_id=manifest.addon_build_id,
        expected_freecad_version=manifest.freecad_version,
        expected_freecad_revision=manifest.freecad_revision,
        expected_profile_path_fingerprint=manifest.profile_path_fingerprint,
    )


def _verify_response(manifest, request, response):
    return verify_handshake_response(
        response,
        secret=SECRET,
        expected_client_nonce=request["client_nonce"],
        expected_profile_id=manifest.profile_id,
        expected_freecad_pid=manifest.freecad_pid,
        expected_freecad_process_started_at=manifest.freecad_process_started_at,
        expected_addon_runtime_id=manifest.addon_runtime_id,
        expected_boot_id=manifest.boot_id,
        expected_rpc_host=manifest.rpc_host,
        expected_rpc_port=manifest.rpc_port,
        expected_protocol_version=manifest.protocol_version,
        expected_protocol_features=manifest.features,
        expected_addon_version=manifest.addon_version,
        expected_addon_build_id=manifest.addon_build_id,
        expected_freecad_version=manifest.freecad_version,
        expected_freecad_revision=manifest.freecad_revision,
        expected_profile_path_fingerprint=manifest.profile_path_fingerprint,
    )


def _expire_and_prune_via_second_handshake(*, ttl: float = 5.0):
    now = [100.0]
    manifest = _manifest()
    manager = SessionManager(
        manifest=manifest,
        secret=SECRET,
        session_ttl_seconds=ttl,
        monotonic=lambda: now[0],
    )
    request_a = _handshake_request(manifest, mcp_runtime_id=MCP_A)
    response_a = manager.perform_handshake(request_a)
    verified_a = _verify_response(manifest, request_a, response_a)
    manager.authenticate(verified_a.session_token, mcp_runtime_id=MCP_A)

    now[0] = 100.0 + ttl
    request_b = _handshake_request(manifest, mcp_runtime_id=MCP_B)
    manager.perform_handshake(request_b)

    with pytest.raises(LeaseProtocolError) as raised:
        manager.authenticate(verified_a.session_token, mcp_runtime_id=MCP_A)
    assert raised.value.code == "INVALID_SESSION"
    return manager, verified_a, raised.value


def _connected_conn(token: str, *, expires_at: str = "2099-01-01T00:00:00Z"):
    conn = FreeCADConnection()
    session = RpcAuthenticationSession()
    session.mark_connected(token, session_id="session-id", expires_at=expires_at)
    configure_rpc_session(conn, session)
    return conn, session


def _context(token: str, *, method: str = "get_gui_state"):
    return RpcAuthenticationContext(
        request_id=str(uuid.uuid4()),
        session_token=token,
        operation_name=method,
    )


def _protocol_error_codes_from_authenticate_sources() -> set[str]:
    """Derive ProtocolError codes reachable from authenticate* only (no hard filter)."""

    source = _SESSION_MANAGER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    target_methods = {"authenticate", "authenticate_envelope"}
    codes: set[str] = set()

    def _collect_raises(node: ast.AST) -> None:
        for child in ast.walk(node):
            if not isinstance(child, ast.Raise) or not isinstance(child.exc, ast.Call):
                continue
            func = child.exc.func
            name = ""
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name not in {"ProtocolError", "_ProtocolError"}:
                continue
            if not child.exc.args:
                continue
            arg0 = child.exc.args[0]
            if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
                codes.add(arg0.value)

    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name in {
            "SessionManager",
            "_SessionManager",
        }:
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if item.name in target_methods:
                        _collect_raises(item)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Flat module layout fallback.
            if node.name in target_methods:
                _collect_raises(node)

    # session_manager.py defines SessionManager as a class; also handle the
    # case where methods live on a nested class under a different name.
    if not codes:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in target_methods:
                    _collect_raises(node)

    return codes


# ---------------------------------------------------------------------------
# WI-3 #1 — anti-drift classification contract
# ---------------------------------------------------------------------------


def test_authenticate_codes_are_explicitly_classified() -> None:
    addon_codes = _protocol_error_codes_from_authenticate_sources()
    assert addon_codes, "failed to derive ProtocolError codes from session_manager.py"

    terminal = {"MISSING_RUNTIME_BINDING"}
    conditional = {"LEASE_PROTOCOL_REQUIRED"}
    recoverable = set(helpers._SESSION_RECOVERABLE_CODES)
    unclassified = addon_codes - recoverable - terminal - conditional
    assert unclassified == set(), (
        f"addon session codes missing client classification: {sorted(unclassified)}"
    )
    # Sanity: the reported bug code must be present and recoverable.
    assert "INVALID_SESSION" in addon_codes
    assert "INVALID_SESSION" in recoverable


def test_new_authenticate_code_would_fail_contract(monkeypatch) -> None:
    """Guard the anti-drift extractor: inventing a code must fail classification."""

    real = _protocol_error_codes_from_authenticate_sources()

    def fake() -> set[str]:
        return set(real) | {"BRAND_NEW_SESSION_CODE"}

    monkeypatch.setattr(
        "tests.test_session_recovery_contract._protocol_error_codes_from_authenticate_sources",
        fake,
    )
    with pytest.raises(AssertionError, match="BRAND_NEW_SESSION_CODE"):
        # Inline the classification that the contract test uses.
        addon_codes = fake()
        terminal = {"MISSING_RUNTIME_BINDING"}
        conditional = {"LEASE_PROTOCOL_REQUIRED"}
        recoverable = set(helpers._SESSION_RECOVERABLE_CODES)
        unclassified = addon_codes - recoverable - terminal - conditional
        assert unclassified == set(), (
            f"addon session codes missing client classification: {sorted(unclassified)}"
        )


# ---------------------------------------------------------------------------
# WI-0 — pre-fix evidence: unfixed classifier leaves INVALID_SESSION hard
# ---------------------------------------------------------------------------


def test_wi0_unfixed_classifier_does_not_recover_invalid_session(monkeypatch) -> None:
    """Reproduce the pre-fix failure mode required by WI-0.

    With the historical two-code allowlist, INVALID_SESSION must reach the
    caller and the refresher must not fire. This locks the diagnosis in CI so
    the gate cannot be skipped silently.
    """

    monkeypatch.setattr(
        helpers,
        "_SESSION_RECOVERABLE_CODES",
        frozenset({"SESSION_EXPIRED", "UNKNOWN_SESSION"}),
    )
    monkeypatch.setattr(
        helpers,
        "_SESSION_EXPIRED_CODES",
        frozenset({"SESSION_EXPIRED", "UNKNOWN_SESSION"}),
    )

    conn, session = _connected_conn("stale-token")
    refresh_calls: list[str] = []

    def refresher() -> None:
        refresh_calls.append("refreshed")
        session.mark_connected(
            "fresh-token",
            session_id=str(uuid.uuid4()),
            expires_at="2099-01-01T00:00:00Z",
        )

    configure_session_refresher(conn, refresher)

    def invoke_rpc(_method, _envelope, *, control=False, timeout=None):
        del control, timeout
        raise JsonRpcRemoteError(
            -32000,
            "RPC session is invalid or no longer available",
            data={"error_code": "INVALID_SESSION"},
        )

    conn.invoke_rpc = invoke_rpc  # type: ignore[method-assign]

    with pytest.raises(JsonRpcRemoteError) as raised:
        connection_invoke_v2_ops.invoke_v2(
            conn, "get_gui_state", {}, _context("stale-token")
        )
    assert raised.value.semantic_code == "INVALID_SESSION"
    assert refresh_calls == []
    conn.disconnect()


# ---------------------------------------------------------------------------
# WI-3 #2 — the reported bug (post-fix recovery)
# ---------------------------------------------------------------------------


def test_invalid_session_after_cross_runtime_prune_recovers() -> None:
    _manager, verified_a, _error = _expire_and_prune_via_second_handshake()
    conn, session = _connected_conn(verified_a.session_token)
    refresh_calls: list[str] = []
    call_tokens: list[str] = []

    def refresher() -> None:
        refresh_calls.append("refreshed")
        session.mark_connected(
            "fresh-token-after-rehandshake",
            session_id=str(uuid.uuid4()),
            expires_at="2099-01-01T00:00:00Z",
        )

    configure_session_refresher(conn, refresher)

    def invoke_rpc(_method, envelope, *, control=False, timeout=None):
        del control, timeout
        token = envelope["session_token"]
        call_tokens.append(token)
        if token == verified_a.session_token:
            raise JsonRpcRemoteError(
                -32000,
                "RPC session is invalid or no longer available",
                data={"error_code": "INVALID_SESSION"},
            )
        return {"ok": True, "result": {"success": True, "active_document": "Demo"}}

    conn.invoke_rpc = invoke_rpc  # type: ignore[method-assign]

    response = connection_invoke_v2_ops.invoke_v2(
        conn,
        "get_gui_state",
        {},
        _context(verified_a.session_token),
    )

    assert response["ok"] is True
    assert refresh_calls == ["refreshed"]
    assert call_tokens == [
        verified_a.session_token,
        "fresh-token-after-rehandshake",
    ]
    assert "INVALID_SESSION" not in str(response)
    conn.disconnect()


# ---------------------------------------------------------------------------
# WI-3 #3 — revoke / binding mismatch recovery
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "code",
    ["SESSION_REVOKED", "SESSION_BINDING_MISMATCH", "SESSION_EXPIRED"],
)
def test_session_codes_trigger_single_rehandshake(code: str) -> None:
    conn, session = _connected_conn("stale-token")
    refresh_calls: list[str] = []

    def refresher() -> None:
        refresh_calls.append(code)
        session.mark_connected(
            "fresh-token",
            session_id=str(uuid.uuid4()),
            expires_at="2099-01-01T00:00:00Z",
        )

    configure_session_refresher(conn, refresher)

    def invoke_rpc(_method, envelope, *, control=False, timeout=None):
        del control, timeout
        if envelope["session_token"] == "stale-token":
            raise JsonRpcRemoteError(
                -32000,
                f"{code}",
                data={"error_code": code},
            )
        return {"ok": True, "result": {"success": True}}

    conn.invoke_rpc = invoke_rpc  # type: ignore[method-assign]
    response = connection_invoke_v2_ops.invoke_v2(
        conn, "get_selection", {}, _context("stale-token", method="get_selection")
    )
    assert response["ok"] is True
    assert refresh_calls == [code]
    conn.disconnect()


# ---------------------------------------------------------------------------
# WI-3 #4 — both refusal shapes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "response, expected",
    [
        ({"ok": False, "error": {"code": "INVALID_SESSION", "message": "gone"}}, "INVALID_SESSION"),
        (
            {
                "success": False,
                "error_code": "SESSION_EXPIRED",
                "error": "RPC session has expired",
            },
            "SESSION_EXPIRED",
        ),
        ({"ok": True, "result": {}}, None),
        ({"ok": False, "error": "plain string"}, None),
    ],
)
def test_invoke_v2_session_error_code_parses_both_shapes(response, expected) -> None:
    assert helpers.invoke_v2_session_error_code(response) == expected


def test_plain_dispatch_shape_triggers_recovery() -> None:
    conn, session = _connected_conn("stale-token")
    refresh_calls: list[str] = []

    def refresher() -> None:
        refresh_calls.append("refreshed")
        session.mark_connected(
            "fresh-token",
            session_id=str(uuid.uuid4()),
            expires_at="2099-01-01T00:00:00Z",
        )

    configure_session_refresher(conn, refresher)

    def invoke_rpc(_method, envelope, *, control=False, timeout=None):
        del control, timeout
        if envelope["session_token"] == "stale-token":
            return {
                "success": False,
                "error_code": "INVALID_SESSION",
                "error": "RPC session is invalid or no longer available",
            }
        return {"ok": True, "result": {"success": True}}

    conn.invoke_rpc = invoke_rpc  # type: ignore[method-assign]
    response = connection_invoke_v2_ops.invoke_v2(
        conn, "get_gui_state", {}, _context("stale-token")
    )
    assert response.get("ok") is True
    assert refresh_calls == ["refreshed"]
    conn.disconnect()


# ---------------------------------------------------------------------------
# WI-3 #5 — AUTHENTICATED_METHODS parametrized recovery (sample + contract)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method", sorted(AUTHENTICATED_METHODS))
def test_authenticated_methods_set_is_nonempty_and_imported(method: str) -> None:
    # Import-based contract: every member is a non-empty RPC method name.
    assert re.fullmatch(r"[a-z][a-z0-9_]*", method)


def _install_recovering_invoke_rpc(conn, session, *, stale: str = "stale-token"):
    refresh_calls: list[str] = []

    def refresher() -> None:
        refresh_calls.append("refreshed")
        session.mark_connected(
            "fresh-token",
            session_id=str(uuid.uuid4()),
            expires_at="2099-01-01T00:00:00Z",
        )

    configure_session_refresher(conn, refresher)

    def invoke_rpc(_method, envelope, *, control=False, timeout=None):
        del control, timeout
        token = envelope["session_token"] if isinstance(envelope, dict) else stale
        if token == stale:
            raise JsonRpcRemoteError(
                -32000,
                "RPC session is invalid or no longer available",
                data={"error_code": "INVALID_SESSION"},
            )
        return {
            "ok": True,
            "result": {"success": True, "recovered": True, "method": envelope.get("method")},
        }

    conn.invoke_rpc = invoke_rpc  # type: ignore[method-assign]
    return refresh_calls


@pytest.mark.parametrize(
    "method,kwargs",
    [
        ("get_gui_state", {}),
        ("get_selection", {}),
        ("get_report_view", {"max_lines": 10, "clear": False}),
        ("activate_document", {"doc_name": "Model"}),
        ("open_document", {"path": "C:/tmp/demo.FCStd"}),
        ("refresh_view", {}),
        ("set_section_view", {"enabled": False}),
        ("set_tree_expanded", {"doc_name": "Model"}),
        ("select_subshapes", {"doc_name": "Model", "selections": []}),
        ("repair_view_placements", {"doc_name": "Model", "touch_objects": ["Box"]}),
        (
            "animate_placement",
            {"doc_name": "Model", "obj_name": "Box", "keyframes": []},
        ),
        ("capture_view_sequence", {"frames": []}),
        ("capture_view_sequence_to_disk", {"frames": [], "frame_dir": "C:/tmp"}),
        ("get_active_screenshot", {"view_name": "Isometric"}),
        ("reload_document", {"doc_name": "Model"}),
    ],
)
def test_gui_connection_bindings_recover_on_invalid_session(method: str, kwargs: dict) -> None:
    """§7.1 #5: recover via real FreeCADConnection bindings, not bare invoke_v2."""

    assert method in GUI_AUTHENTICATED_METHODS
    conn, session = _connected_conn("stale-token")
    refresh_calls = _install_recovering_invoke_rpc(conn, session)
    bound = getattr(conn, method)
    result = bound(**kwargs) if kwargs else bound()
    assert refresh_calls == ["refreshed"]
    if method == "get_active_screenshot":
        # Screenshot unwrap yields a string (or None on soft failure).
        assert result is None or isinstance(result, str)
    else:
        assert isinstance(result, dict)
        assert result.get("success") is True or result.get("recovered") is True
        assert "INVALID_SESSION" not in str(result)
    conn.disconnect()


def test_every_gui_auth_binding_source_routes_through_invoke_v2() -> None:
    """Generated + shim GUI bindings must contain _invoke_mutation_v2 (no dual-path drift)."""

    import inspect

    from freecad_mcp.generated.capabilities.connection_methods import (
        connection_view_ops as generated_view,
    )
    from freecad_mcp.generated.capabilities.connection_methods import (
        connection_read_ops as generated_read,
    )

    for method in sorted(GUI_AUTHENTICATED_METHODS):
        if method == "reload_document":
            func = getattr(generated_read, method)
        else:
            func = getattr(generated_view, method)
        source = inspect.getsource(func)
        assert "_invoke_mutation_v2" in source, (
            f"{method} generated binding lacks _invoke_mutation_v2 routing"
        )


def test_live_non_gui_auth_bindings_route_through_invoke_v2() -> None:
    """Save/control bindings that remain live must use invoke_v2 recovery."""

    import inspect

    from freecad_mcp.generated.capabilities.connection_methods import (
        connection_control_ops as generated_control,
    )
    from freecad_mcp.generated.capabilities.connection_methods import (
        connection_save_ops as generated_save,
    )

    checks = {
        "save_document": (generated_save, ("_invoke_mutation_v2",)),
        "save_document_as": (generated_save, ("_invoke_mutation_v2",)),
        "finalize_document_edit": (generated_save, ("_invoke_mutation_v2",)),
        "get_request_status": (generated_control, ("invoke_v2",)),
        "cancel_request": (generated_control, ("invoke_v2",)),
        "notify_cancel_request": (
            generated_control,
            ("_refreshed_context", "notification=True", "invoke_rpc"),
        ),
    }
    for method, (module, needles) in checks.items():
        source = inspect.getsource(getattr(module, method))
        missing = [needle for needle in needles if needle not in source]
        assert not missing, (
            f"{method} binding missing recovery markers: {missing}"
        )
        if method == "notify_cancel_request":
            assert "invoke_v2(" not in source.replace("invoke_v2_control", "")


def test_notify_cancel_request_always_refreshes_before_send() -> None:
    """Notifications cannot surface INVALID_SESSION; pre-send refresh is mandatory."""

    from freecad_mcp.freecad_client_ops.connection_methods.connection_control_ops import (
        notify_cancel_request,
    )

    conn, session = _connected_conn("stale-token")
    refresh_calls: list[str] = []

    def refresher() -> None:
        refresh_calls.append("refreshed")
        session.mark_connected(
            "fresh-token",
            session_id=str(uuid.uuid4()),
            expires_at="2099-01-01T00:00:00Z",
        )

    configure_session_refresher(conn, refresher)
    envelopes: list[dict] = []

    def invoke_rpc(method, envelope, *, control=False, timeout=None, notification=False):
        del control, timeout
        assert method == "invoke_v2_control"
        assert notification is True
        envelopes.append(envelope)
        return None

    conn.invoke_rpc = invoke_rpc  # type: ignore[method-assign]
    assert (
        notify_cancel_request(conn, "4d70e4e7-9bd8-410b-bd73-f5e49eb60cb5") is True
    )
    assert refresh_calls == ["refreshed"]
    assert envelopes and envelopes[0]["session_token"] == "fresh-token"
    conn.disconnect()


def test_client_gui_lane_set_matches_addon() -> None:
    assert helpers._session_recovery_lane("get_gui_state", control=False) == "gui"
    assert helpers._session_recovery_lane("save_document", control=False) == "mutation"
    for method in GUI_AUTHENTICATED_METHODS:
        assert helpers._session_recovery_lane(method, control=True) == "gui"


@pytest.mark.parametrize("method", sorted(AUTHENTICATED_METHODS))
def test_authenticated_methods_recover_via_invoke_v2_lane(method: str) -> None:
    """§7.1 #5: every AUTHENTICATED_METHODS member recovers on INVALID_SESSION."""

    conn, session = _connected_conn("stale-token")
    refresh_calls = _install_recovering_invoke_rpc(conn, session)
    response = connection_invoke_v2_ops.invoke_v2(
        conn, method, {}, _context("stale-token", method=method)
    )
    assert response["ok"] is True
    assert refresh_calls == ["refreshed"]
    conn.disconnect()


def test_save_document_dispatch_lane_is_mutation(monkeypatch, tmp_path) -> None:
    import os
    from types import SimpleNamespace

    from addon.FreeCADMCP.rpc_server.methods.dispatch_helpers_ops.dispatch_core import (
        dispatch as dispatch_core,
    )

    log_path = tmp_path / "auth.jsonl"
    monkeypatch.setenv("FREECAD_MCP_ADDON_TELEMETRY_FILE", str(log_path))

    identity = {"instance_id": "runtime-1", "request_id": str(uuid.uuid4())}
    stored = dict(identity)
    collaborators = SimpleNamespace(
        request_identity_provider=lambda: SimpleNamespace(
            get_request_identity=lambda: dict(stored),
            set_request_identity=lambda **values: stored.update(values),
        ),
        session_manager=None,
        lease_protocol_public_error=lambda exc, request_id=None: {
            "error": {"code": "LEASE_PROTOCOL_ERROR", "message": str(exc)},
            "request_id": request_id,
        },
    )
    facade = SimpleNamespace(
        _execution_collaborators=collaborators,
        save_document=lambda *_a, **_k: pytest.fail("must not call"),
    )
    result = dispatch_core(facade, "save_document", ("Model",))
    assert result["error_code"] == "LEASE_PROTOCOL_REQUIRED"
    text = log_path.read_text(encoding="utf-8")
    assert "auth_gate_refused" in text
    assert '"lane":"mutation"' in text or '"lane": "mutation"' in text
    assert os.environ.get("FREECAD_MCP_ADDON_TELEMETRY_FILE")


def test_failed_rehandshake_surfaces_protocol_code_and_lane() -> None:
    from freecad_mcp.freecad_client_ops.rpc_invocation_error import RpcInvocationError

    conn, session = _connected_conn("stale-token")

    def refresher() -> None:
        raise RuntimeError("handshake blew up")

    configure_session_refresher(conn, refresher)

    def invoke_rpc(_method, _envelope, *, control=False, timeout=None):
        del control, timeout
        raise JsonRpcRemoteError(
            -32000,
            "gone",
            data={"error_code": "INVALID_SESSION"},
        )

    conn.invoke_rpc = invoke_rpc  # type: ignore[method-assign]
    with pytest.raises(RpcInvocationError) as raised:
        connection_invoke_v2_ops.invoke_v2(
            conn, "get_gui_state", {}, _context("stale-token")
        )
    assert raised.value.protocol_code == "INVALID_SESSION"
    assert raised.value.lane == "gui"
    assert "INVALID_SESSION" in str(raised.value)
    conn.disconnect()


def test_proactive_refresh_failure_falls_back_to_reactive_retry() -> None:
    soon = (datetime.now(UTC) + timedelta(seconds=30)).isoformat().replace("+00:00", "Z")
    conn, session = _connected_conn("about-to-expire", expires_at=soon)
    attempts = {"n": 0}

    def refresher() -> None:
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RuntimeError("transient handshake failure")
        session.mark_connected(
            "fresh-token",
            session_id=str(uuid.uuid4()),
            expires_at="2099-01-01T00:00:00Z",
        )

    configure_session_refresher(conn, refresher)

    def invoke_rpc(_method, envelope, *, control=False, timeout=None):
        del control, timeout
        if envelope["session_token"] == "about-to-expire":
            raise JsonRpcRemoteError(
                -32000,
                "expired",
                data={"error_code": "SESSION_EXPIRED"},
            )
        return {"ok": True, "result": {"success": True}}

    conn.invoke_rpc = invoke_rpc  # type: ignore[method-assign]
    response = connection_invoke_v2_ops.invoke_v2(
        conn, "get_gui_state", {}, _context("about-to-expire")
    )
    assert response["ok"] is True
    assert attempts["n"] == 2
    conn.disconnect()


# ---------------------------------------------------------------------------
# WI-3 #6 — cross-runtime prune must not strand the first runtime
# ---------------------------------------------------------------------------


def test_second_runtime_handshake_does_not_strand_first_client() -> None:
    test_invalid_session_after_cross_runtime_prune_recovers()


# ---------------------------------------------------------------------------
# WI-3 #7 — proactive refresh skew
# ---------------------------------------------------------------------------


def test_proactive_refresh_fires_inside_skew_margin() -> None:
    soon = (datetime.now(UTC) + timedelta(seconds=30)).isoformat().replace("+00:00", "Z")
    conn, session = _connected_conn("about-to-expire", expires_at=soon)
    refresh_calls: list[str] = []

    def refresher() -> None:
        refresh_calls.append("proactive")
        session.mark_connected(
            "fresh-token",
            session_id=str(uuid.uuid4()),
            expires_at="2099-01-01T00:00:00Z",
        )

    configure_session_refresher(conn, refresher)

    def invoke_rpc(_method, envelope, *, control=False, timeout=None):
        del control, timeout
        assert envelope["session_token"] == "fresh-token"
        return {"ok": True, "result": {"success": True}}

    conn.invoke_rpc = invoke_rpc  # type: ignore[method-assign]
    response = connection_invoke_v2_ops.invoke_v2(
        conn, "get_gui_state", {}, _context("about-to-expire")
    )
    assert response["ok"] is True
    assert refresh_calls == ["proactive"]
    conn.disconnect()


def test_proactive_refresh_skips_outside_skew_margin() -> None:
    later = (datetime.now(UTC) + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    conn, session = _connected_conn("still-fresh", expires_at=later)
    refresh_calls: list[str] = []

    def refresher() -> None:
        refresh_calls.append("should-not-fire")

    configure_session_refresher(conn, refresher)

    def invoke_rpc(_method, envelope, *, control=False, timeout=None):
        del control, timeout
        assert envelope["session_token"] == "still-fresh"
        return {"ok": True, "result": {"success": True}}

    conn.invoke_rpc = invoke_rpc  # type: ignore[method-assign]
    response = connection_invoke_v2_ops.invoke_v2(
        conn, "get_gui_state", {}, _context("still-fresh")
    )
    assert response["ok"] is True
    assert refresh_calls == []
    conn.disconnect()


def test_proactive_refresh_skips_unparseable_expiry() -> None:
    conn, session = _connected_conn("token", expires_at="not-a-timestamp")
    refresh_calls: list[str] = []

    def refresher() -> None:
        refresh_calls.append("should-not-fire")

    configure_session_refresher(conn, refresher)

    def invoke_rpc(_method, _envelope, *, control=False, timeout=None):
        del control, timeout
        return {"ok": True, "result": {"success": True}}

    conn.invoke_rpc = invoke_rpc  # type: ignore[method-assign]
    connection_invoke_v2_ops.invoke_v2(conn, "get_gui_state", {}, _context("token"))
    assert refresh_calls == []
    conn.disconnect()


# ---------------------------------------------------------------------------
# WI-3 #8 — LEASE_PROTOCOL_REQUIRED conditional recovery
# ---------------------------------------------------------------------------


def test_lease_protocol_required_retries_when_token_held() -> None:
    conn, session = _connected_conn("held-token")
    refresh_calls: list[str] = []

    def refresher() -> None:
        refresh_calls.append("refreshed")
        session.mark_connected(
            "fresh-token",
            session_id=str(uuid.uuid4()),
            expires_at="2099-01-01T00:00:00Z",
        )

    configure_session_refresher(conn, refresher)

    def invoke_rpc(_method, envelope, *, control=False, timeout=None):
        del control, timeout
        if envelope["session_token"] == "held-token":
            raise JsonRpcRemoteError(
                -32000,
                "handshake required",
                data={"error_code": "LEASE_PROTOCOL_REQUIRED"},
            )
        return {"ok": True, "result": {"success": True}}

    conn.invoke_rpc = invoke_rpc  # type: ignore[method-assign]
    response = connection_invoke_v2_ops.invoke_v2(
        conn, "get_gui_state", {}, _context("held-token")
    )
    assert response["ok"] is True
    assert refresh_calls == ["refreshed"]
    conn.disconnect()


def test_lease_protocol_required_does_not_retry_without_token_classification() -> None:
    assert (
        helpers.is_recoverable_session_error(
            "LEASE_PROTOCOL_REQUIRED",
            has_session_token=False,
        )
        is False
    )
    assert (
        helpers.is_recoverable_session_error(
            "LEASE_PROTOCOL_REQUIRED",
            has_session_token=True,
        )
        is True
    )


# ---------------------------------------------------------------------------
# WI-4 smoke — auth gate refusal emits telemetry event
# ---------------------------------------------------------------------------


def test_auth_gate_refusal_emits_debug_record(monkeypatch, tmp_path) -> None:
    import os
    from types import SimpleNamespace

    from addon.FreeCADMCP.rpc_server.methods.dispatch_helpers_ops.dispatch_core import (
        dispatch as dispatch_core,
    )

    log_path = tmp_path / "auth.jsonl"
    monkeypatch.setenv("FREECAD_MCP_ADDON_TELEMETRY_FILE", str(log_path))
    monkeypatch.delenv("FREECAD_MCP_TELEMETRY", raising=False)

    identity = {"instance_id": "runtime-1", "request_id": str(uuid.uuid4())}
    stored = dict(identity)

    collaborators = SimpleNamespace(
        request_identity_provider=lambda: SimpleNamespace(
            get_request_identity=lambda: dict(stored),
            set_request_identity=lambda **values: stored.update(values),
        ),
        session_manager=None,
        lease_protocol_public_error=lambda exc, request_id=None: {
            "error": {"code": "LEASE_PROTOCOL_ERROR", "message": str(exc)},
            "request_id": request_id,
        },
    )
    facade = SimpleNamespace(
        _execution_collaborators=collaborators,
        get_gui_state=lambda: pytest.fail("must not call handler"),
    )

    result = dispatch_core(facade, "get_gui_state", ())
    assert result["error_code"] == "LEASE_PROTOCOL_REQUIRED"
    assert log_path.is_file(), f"telemetry file missing; env={os.environ.get('FREECAD_MCP_ADDON_TELEMETRY_FILE')}"
    text = log_path.read_text(encoding="utf-8")
    assert "auth_gate_refused" in text
    assert "LEASE_PROTOCOL_REQUIRED" in text
    assert '"lane":"gui"' in text or '"lane": "gui"' in text
    assert "get_gui_state" in text