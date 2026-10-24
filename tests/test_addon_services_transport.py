"""MCP, client shape, cached metadata and transport admission contracts."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from freecad_mcp.freecad_client import FreeCADConnection
from addon.FreeCADMCP.rpc_server.methods import addon_services as rpc
from addon.FreeCADMCP.rpc_server.methods.v2_methods_ops.envelope_params import ordered_envelope_params
from addon.FreeCADMCP.rpc_server.rpc_server_ops.facade_bindings import bind_freecad_rpc
from addon.FreeCADMCP import automation_pause
from tests.helpers.addon_services import NativeDocument, host, registry_with

pytestmark = pytest.mark.unit


def test_cached_metadata_needs_no_gui_document_or_provider_execution():
    callback = Mock()
    service, lookup, _ = host(NativeDocument(), registry_with(callback))
    service._dispatch_gui = Mock(side_effect=AssertionError("metadata dispatched to GUI"))
    assert service._dispatch("list_addons", ())["addons"] == [
        {"addon_id": "Example", "version": "1", "protocol_version": 1}]
    assert service._dispatch("describe_addon", ("Example",))["addon"]["operations"][0]["name"] == "run"
    assert service.describe_addon("Missing")["error_code"] == "ADDON_NOT_FOUND"
    assert service.describe_addon([])["error_code"] == "INVALID_ARGUMENT"
    lookup.assert_not_called()
    callback.assert_not_called()


def test_transport_authentication_refuses_before_native_or_provider():
    callback = Mock()
    service, lookup, _ = host(NativeDocument(), registry_with(callback))
    service._execution_collaborators = SimpleNamespace(
        session_manager=object(), request_identity_provider=lambda: SimpleNamespace(get_request_identity=lambda: {}))
    result = service._dispatch("invoke_addon_operation", ("Target", "Example", "run", {"value": 1}))
    assert result["error_code"] == "LEASE_PROTOCOL_REQUIRED"
    lookup.assert_not_called()
    callback.assert_not_called()


def test_pause_blocks_invocation_but_allows_cached_metadata():
    callback = Mock()
    service, lookup, _ = host(NativeDocument(), registry_with(callback))
    automation_pause.request_local_pause_after_current()
    try:
        result = service._dispatch("invoke_addon_operation", ("Target", "Example", "run", {"value": 1}))
        assert result["error_code"] == "AUTOMATION_PAUSED"
        assert service._dispatch("list_addons", ())["success"] is True
    finally:
        automation_pause._paused = False
    lookup.assert_not_called()
    callback.assert_not_called()


def test_client_v2_shape_preserves_nested_arguments_and_document_scope():
    conn = SimpleNamespace(server=Mock(), _invoke_mutation_v2=Mock(return_value={"success": True}))
    arguments = {"value": 1}
    assert FreeCADConnection.invoke_addon_operation(conn, "Target", "Example", "run", arguments) == {"success": True}
    conn._invoke_mutation_v2.assert_called_once_with("invoke_addon_operation", {
        "doc_name": "Target", "addon_id": "Example", "operation": "run", "arguments": arguments},
        document_names=("Target",), operation_name="Invoke add-on operation")
    conn.server.invoke_addon_operation.assert_not_called()
    service, _, _ = host(NativeDocument(), registry_with(Mock()))
    params = ordered_envelope_params(service.invoke_addon_operation, {
        "arguments": arguments, "operation": "run", "addon_id": "Example", "doc_name": "Target"})
    assert params == ("Target", "Example", "run", arguments)


def test_public_rpc_facade_binds_shared_handlers():
    class FreeCADRPC:
        pass
    bind_freecad_rpc(FreeCADRPC)
    assert FreeCADRPC.list_addons is rpc.list_addons
    assert FreeCADRPC.describe_addon is rpc.describe_addon
    assert FreeCADRPC.invoke_addon_operation is rpc.invoke_addon_operation




@pytest.mark.parametrize("response", [None, {"success": True},
    {"success": True, "committed": False, "outcome": "committed"},
    {"success": True, "committed": True, "outcome": "queued"}])
def test_mcp_adapter_rejects_unproven_success(response):
    from freecad_mcp.operations.core_ops.addon_ops import invoke_addon_operation_operation
    conn = SimpleNamespace(invoke_addon_operation=Mock(return_value=response))
    result = invoke_addon_operation_operation(conn, "Target", "Example", "run", {})
    assert result.isError
    assert result.structuredContent["data"]["outcome"] == "uncertain"
    assert result.structuredContent["data"]["committed"] is None


def test_mcp_adapter_preserves_committed_json_result():
    from freecad_mcp.operations.core_ops.addon_ops import invoke_addon_operation_operation
    payload = {"success": True, "committed": True, "outcome": "committed", "result": {"job_id": "opaque"}}
    result = invoke_addon_operation_operation(
        SimpleNamespace(invoke_addon_operation=Mock(return_value=payload)), "Target", "Example", "run", {})
    assert not result.isError
    assert result.structuredContent["data"] == payload
