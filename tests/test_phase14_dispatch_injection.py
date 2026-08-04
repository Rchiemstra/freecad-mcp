from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.methods.dispatch_helpers_ops.dispatch_core_unenforced import (
    import_document_lock_or_none,
)
from addon.FreeCADMCP.rpc_server.methods.dispatch_helpers_ops.credential_inflight import (
    model_credential,
)
from addon.FreeCADMCP.rpc_server.methods.dispatch_helpers_ops.dispatch_core_enforcement_auth import (
    authenticate_session_or_error,
)
from addon.FreeCADMCP.rpc_server.methods.lease_methods_ops.heartbeat import (
    lease_heartbeat_batch,
)
from addon.FreeCADMCP.rpc_server.methods.lifecycle_methods_ops.control_status import (
    get_instance_info,
)
from addon.FreeCADMCP.rpc_server.methods.v2_methods_ops.handshake import handshake_v2
from addon.FreeCADMCP.rpc_server.methods.v2_methods_ops.invoke_v2_control import (
    invoke_v2_control,
)
from addon.FreeCADMCP.rpc_server.methods.v2_methods_ops.invoke_v2_finalize import (
    apply_acquisition_escrow,
)

pytestmark = pytest.mark.unit


ROOT = Path(__file__).parents[1]
OWNED_PRODUCTION = (
    ROOT
    / "addon/FreeCADMCP/rpc_server/methods/dispatch_helpers_ops",
    ROOT / "addon/FreeCADMCP/rpc_server/methods/v2_methods_ops",
)
OWNED_FILES = (
    ROOT
    / "addon/FreeCADMCP/rpc_server/methods/lifecycle_methods_ops/control_cancel.py",
    ROOT
    / "addon/FreeCADMCP/rpc_server/methods/lifecycle_methods_ops/control_cancel_finalize.py",
    ROOT
    / "addon/FreeCADMCP/rpc_server/methods/lifecycle_methods_ops/control_cancel_handoff.py",
    ROOT
    / "addon/FreeCADMCP/rpc_server/methods/lifecycle_methods_ops/control_status.py",
    ROOT
    / "addon/FreeCADMCP/rpc_server/methods/lifecycle_methods_ops/control_status_state.py",
    ROOT / "addon/FreeCADMCP/rpc_server/methods/lease_methods_ops/heartbeat.py",
)


def _owned_python_files() -> tuple[Path, ...]:
    nested = tuple(
        path
        for directory in OWNED_PRODUCTION
        for path in sorted(directory.glob("*.py"))
    )
    return (*nested, *OWNED_FILES)


def test_phase14_dispatch_slice_has_no_runtime_module_locator_or_freecad_proxy() -> None:
    for path in _owned_python_files():
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        assert not any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "_rpc_mod"
            for node in ast.walk(tree)
        ), path
        assert not any(
            isinstance(node, ast.Name) and node.id == "_rpc_mod"
            for node in ast.walk(tree)
        ), path
        assert not any(
            isinstance(node, ast.ImportFrom)
            and (node.module or "").endswith(("lease_runtime", "settings"))
            for node in ast.walk(tree)
        ), path
        assert "_FreeCADProxy" not in source, path

    status_tree = ast.parse(
        OWNED_FILES[3].read_text(encoding="utf-8"), filename=str(OWNED_FILES[3])
    )
    forbidden_status_providers = {
        "_process_started_at",
        "_boot_identity",
        "_profile_fingerprint",
    }
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in forbidden_status_providers
        for node in ast.walk(status_tree)
    )

    finalize_path = (
        ROOT
        / "addon/FreeCADMCP/rpc_server/methods/v2_methods_ops/invoke_v2_finalize.py"
    )
    finalize_tree = ast.parse(
        finalize_path.read_text(encoding="utf-8"), filename=str(finalize_path)
    )
    assert not any(isinstance(node, ast.Import) for node in ast.walk(finalize_tree))


def test_document_lock_import_uses_the_exact_injected_callable() -> None:
    sentinel = object()
    calls: list[str] = []
    collaborators = SimpleNamespace(
        import_document_lock=lambda: calls.append("import") or sentinel
    )

    assert import_document_lock_or_none(collaborators) is sentinel
    assert calls == ["import"]


def test_handshake_uses_only_the_injected_session_and_public_error() -> None:
    payload = object()
    expected = object()
    calls: list[tuple[str, object]] = []
    collaborators = SimpleNamespace(
        session_manager=SimpleNamespace(
            perform_handshake=lambda value: calls.append(("handshake", value))
            or expected
        ),
        lease_protocol_public_error=lambda exc: calls.append(("error", exc)),
    )
    facade = SimpleNamespace(_execution_collaborators=collaborators)

    assert handshake_v2(facade, payload) is expected
    assert calls == [("handshake", payload)]


def test_authentication_failure_uses_the_exact_injected_public_error() -> None:
    failure = RuntimeError("private auth failure")
    calls = []

    def authenticate(*_args, **_kwargs):
        raise failure

    def public_error(exc, *, request_id=None):
        calls.append((exc, request_id))
        return {
            "error": {"code": "AUTH_FAILED", "message": "safe"},
            "request_id": request_id,
        }

    collaborators = SimpleNamespace(
        session_manager=SimpleNamespace(authenticate=authenticate),
        lease_protocol_public_error=public_error,
    )
    identity = {
        "rpc_session_token": "token",
        "instance_id": "runtime-1",
        "request_id": "request-1",
    }

    assert authenticate_session_or_error(
        collaborators, SimpleNamespace(), identity
    ) == {
        "success": False,
        "error_code": "AUTH_FAILED",
        "error": "safe",
        "request_id": "request-1",
    }
    assert calls == [(failure, "request-1")]


def test_model_credential_uses_the_exact_injected_lease_constructor() -> None:
    calls = []
    expected = object()

    def lease_credential(**kwargs):
        calls.append(kwargs)
        return expected

    facade = SimpleNamespace(
        _execution_collaborators=SimpleNamespace(
            import_document_lease=lambda: SimpleNamespace(
                LeaseCredential=lease_credential
            )
        )
    )
    inflight = SimpleNamespace(
        lease_id="lease-1",
        document_session_uuid="document-1",
        generation=3,
        token="secret",
        mcp_instance_id="runtime-1",
    )

    assert model_credential(facade, inflight) is expected
    assert calls == [
        {
            "lease_id": "lease-1",
            "document_session_uuid": "document-1",
            "generation": 3,
            "token": "secret",
            "mcp_instance_id": "runtime-1",
        }
    ]


def test_control_lane_rejection_uses_the_injected_public_error() -> None:
    calls = []

    def public_error(exc, *, request_id=None):
        calls.append((exc, request_id))
        return {"mapped": True}

    facade = SimpleNamespace(
        _execution_collaborators=SimpleNamespace(
            lease_protocol_public_error=public_error
        )
    )

    assert invoke_v2_control(
        facade, {"method": "shutdown_rpc_server", "request_id": "request-1"}
    ) == {"mapped": True}
    assert len(calls) == 1
    assert calls[0][0].code == "METHOD_NOT_CONTROL"
    assert calls[0][1] == "request-1"


def test_heartbeat_uses_injected_control_dependencies_by_identity() -> None:
    credential = object()
    status = {"state": "LOCKED_IDLE"}
    calls = []

    class LeaseService:
        def heartbeat(self, supplied, *, current_operation):
            calls.append(("heartbeat", supplied, current_operation))
            return dict(status)

    collaborators = SimpleNamespace(
        document_lease_service=LeaseService(),
        import_document_lock=lambda: SimpleNamespace(
            get_request_identity=lambda: {"request_id": "request-1"}
        ),
        credential_from_wire=lambda item: calls.append(("credential", item))
        or credential,
        redact_rpc_diagnostic=lambda value, **_kwargs: f"safe:{value}",
        lease_service_error=lambda *_args, **_kwargs: {"success": False},
    )
    facade = SimpleNamespace(_execution_collaborators=collaborators)
    item = {
        "document_session_uuid": "document-1",
        "current_operation": "editing",
    }

    assert lease_heartbeat_batch(facade, [item]) == {
        "success": True,
        "leases": [{"state": "LOCKED_IDLE", "success": True}],
    }
    assert calls == [
        ("credential", item),
        ("heartbeat", credential, "safe:editing"),
    ]


def test_instance_info_uses_eager_injected_status_values() -> None:
    collaborators = SimpleNamespace(
        load_settings=lambda: {
            "profile_instance_id": "profile-1",
            "document_lease_mode": "enforce",
        },
        freecad=SimpleNamespace(getUserAppDataDir=lambda: "/profile/"),
        freecad_version_parts=lambda: ("1", "2", "3"),
        actual_endpoint={"host": "127.0.0.1", "port": 9000},
        runtime_id="runtime-1",
        runtime_manifest=None,
        process_started_at="process-start",
        boot_id="boot-1",
        addon_loaded_at="addon-start",
        server_started_at="rpc-start",
        session_manager=object(),
        profile_fingerprint="profile-fingerprint",
    )

    result = get_instance_info(
        SimpleNamespace(_execution_collaborators=collaborators)
    )

    assert result["freecad_process_started_at"] == "process-start"
    assert result["boot_id"] == "boot-1"
    assert result["profile_path_fingerprint"] == "profile-fingerprint"
    assert result["actual_endpoint"] is collaborators.actual_endpoint


def test_acquisition_escrow_uses_the_exact_injected_logger() -> None:
    calls = []

    class FailingStore:
        def store(self, **_kwargs):
            raise RuntimeError("private escrow failure")

    logger = SimpleNamespace(
        exception=lambda message, request_id: calls.append((message, request_id))
    )
    collaborators = SimpleNamespace(
        acquisition_claim_store=FailingStore(),
        logger=logger,
    )
    result = {"success": True, "credential": {"token": "secret"}}
    envelope = SimpleNamespace(request_id="request-1", method="acquire_document_lock")
    session = SimpleNamespace(mcp=SimpleNamespace(runtime_id="runtime-1"))

    response, cached = apply_acquisition_escrow(
        collaborators=collaborators,
        response={"ok": True, "result": result},
        result=result,
        envelope=envelope,
        session=session,
        invocation_runtime_id="addon-runtime-1",
    )

    assert response["result"]["error_code"] == "ACQUISITION_CREDENTIAL_ESCROW_FAILED"
    assert cached is response
    assert calls == [
        ("Failed to retain private acquisition claim for %s", "request-1")
    ]
