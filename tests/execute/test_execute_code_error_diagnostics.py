"""Keep execute_code failure evidence through the JSON-RPC and MCP boundaries."""
from __future__ import annotations

import io
from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.execute_code_gui_exec import run_python_on_gui_thread
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.execute_code_response import finalize_gui_execute_response
from addon.FreeCADMCP.transport.json_rpc_errors import json_rpc_error_from_result
from freecad_mcp._shared.protocol.json_rpc_client import JsonRpcRemoteError
from freecad_mcp.operations.core_ops.execute_ops import execute_code_operation

pytestmark = pytest.mark.unit


@pytest.mark.parametrize('exception', ['AssertionError', 'TimeoutError', 'ConnectionResetError'])
def test_message_less_python_exception_reaches_rpc_message(exception):
    app = SimpleNamespace(Console=SimpleNamespace(PrintMessage=lambda _: None, PrintError=lambda _: None))
    ok, traceback = run_python_on_gui_thread(f'raise {exception}()', io.StringIO(), freecad=app)
    assert not ok
    failure = finalize_gui_execute_response(lambda result: result,
        {'ok': False, 'error': traceback['message'], 'traceback': traceback}, {})
    error = json_rpc_error_from_result(failure)
    assert exception in error['message']
    assert '<string>:1' in error['message']
    assert error['data']['traceback'] == traceback


@pytest.mark.parametrize('failure', [
    {'success': False, 'error_code': 'GUI_DISPATCH_FAILED', 'error': 'Timed out after 120s waiting for FreeCAD GUI response', 'timeout_stage': 'executing'},
    {'success': False, 'error_code': 'worker_timeout', 'error': 'Worker execution timed out'},
    {'success': False, 'error_code': 'SESSION_INVALID', 'error': 'Session belongs to a previous runtime'},
    {'success': False, 'error': {'type': 'ConnectionResetError', 'message': ''}},
])
def test_remote_execution_failure_keeps_structured_cause_in_mcp(failure):
    error = json_rpc_error_from_result(failure)
    if isinstance(failure['error'], dict):
        assert 'ConnectionResetError' in error['message']
    remote = JsonRpcRemoteError(error['code'], error['message'], data=error['data'], request_id='rpc-1')

    def execute(*_):
        raise remote

    result = execute_code_operation(SimpleNamespace(execute_code=execute), True, 'pass')
    assert result.isError
    assert result.structuredContent['data'] == error['data']
    assert error['message'] in result.content[0].text


@pytest.mark.parametrize('exception', [TimeoutError, ConnectionResetError, OSError])
def test_message_less_transport_exception_keeps_its_type(exception):
    def execute(*_):
        raise exception()

    result = execute_code_operation(SimpleNamespace(execute_code=execute), True, 'pass')
    assert result.isError
    assert exception.__name__ in result.content[0].text
