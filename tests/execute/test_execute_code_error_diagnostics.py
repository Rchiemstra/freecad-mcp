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
    safe_trace = error['data']['traceback']
    assert safe_trace['exception_type'] == traceback['exception_type']
    assert safe_trace['frames'][-1]['line'] == traceback['frames'][-1]['line']
    assert not safe_trace['frames'][-1]['code']


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


def test_source_is_not_in_public_message_or_log(caplog):
    source = "assert False, 'source-only-literal'"
    failure = {'ok': False, 'error': '', 'traceback': {
        'exception_type': 'AssertionError', 'message': '',
        'traceback': '  ' + source, 'line_code': source,
        'frames': [{'file': '<string>', 'line': 17, 'code': source}]}}
    error = json_rpc_error_from_result(failure)
    assert error['message'] == 'AssertionError at <string>:17'
    remote = JsonRpcRemoteError(error['code'], error['message'], data=error['data'])
    def execute(*_):
        raise remote
    result = execute_code_operation(SimpleNamespace(execute_code=execute), True, source)
    assert source not in str(error)
    assert source not in str(result)
    assert source not in caplog.text
    # An older peer may already have appended the failing source to its message.
    remote = JsonRpcRemoteError(-32000, 'AssertionError at <string>:17: ' + source, data=failure)
    result = execute_code_operation(SimpleNamespace(execute_code=execute), True, source)
    assert source not in str(result)
    assert source not in caplog.text


def test_known_secrets_are_scrubbed_everywhere(caplog):
    secret = 'job68-private-credential'
    failure = {'ok': False, 'error_code': 'DOCUMENT_CONFLICT',
               'error': f'ValueError: {secret}', 'token': secret,
               'stdout': f'printed {secret}', 'details': {secret: secret},
               'traceback': {'exception_type': 'ValueError', 'message': secret,
                             'frames': [{'file': secret, 'line': 9, 'code': secret}]}}
    error = json_rpc_error_from_result(failure)
    assert secret not in str(error)
    # Also sanitize an old/untrusted peer independently at the MCP boundary.
    remote = JsonRpcRemoteError(-32001, failure['error'], data=failure)
    def execute(*_):
        raise remote
    result = execute_code_operation(SimpleNamespace(execute_code=execute), True, 'pass')
    assert secret not in str(result)
    assert secret not in caplog.text
    assert result.structuredContent['error_code'] == 'DOCUMENT_CONFLICT'


def test_diagnostic_fields_and_total_are_bounded_preserving_types():
    import json
    huge = '\\u2603' * 100000
    failure = {'success': False, 'error_code': 'STALE_REVISION', 'error': huge,
               'stdout': huge, 'stderr': huge, 'details': {'many': [huge] * 100},
               'traceback': {'exception_type': 'ValueError', 'message': huge,
                             'frames': [{'file': huge, 'line': 42, 'code': huge}] * 100}}
    error = json_rpc_error_from_result(failure)
    assert error['code'] == -32002
    assert error['data']['error_code'] == 'STALE_REVISION'
    assert isinstance(error['data']['stdout'], str)
    assert isinstance(error['data']['traceback'], dict)
    assert isinstance(error['data']['traceback']['frames'], list)
    assert isinstance(error['data']['traceback']['frames'][0]['line'], int)
    assert len(error['message'].encode()) <= 2048
    assert len(json.dumps(error).encode()) <= 32768
    remote = JsonRpcRemoteError(-32002, huge, data=failure)
    def execute(*_):
        raise remote
    result = execute_code_operation(SimpleNamespace(execute_code=execute), True, 'pass')
    assert len(str(result).encode()) <= 65536
    assert result.structuredContent['error_code'] == 'STALE_REVISION'


@pytest.mark.parametrize(('semantic', 'numeric'), [
    ('DOCUMENT_CONFLICT', -32001), ('STALE_REVISION', -32002),
    ('REQUEST_CANCELLED', -32003), ('DOCUMENT_CLOSE_REJECTED', -32004),
    ('GUI_DISPATCH_FAILED', -32000)])
def test_diagnostics_preserve_error_code_contract(semantic, numeric):
    error = json_rpc_error_from_result({'ok': False, 'error_code': semantic,
                                      'error': {'code': semantic, 'message': 'ValueError: bad value'}})
    assert error['code'] == numeric
    assert isinstance(error['code'], int)
    assert error['data']['error_code'] == semantic
    assert isinstance(error['message'], str)


def test_exception_with_message_keeps_type_message_and_line():
    error = json_rpc_error_from_result({
        'ok': False, 'error': 'bad value', 'traceback': {
            'exception_type': 'ValueError', 'message': 'bad value',
            'frames': [{'file': '<string>', 'line': 23, 'code': 'private source'}]}})
    assert error['message'] == 'ValueError at <string>:23: bad value'


def test_known_environment_credential_is_scrubbed_from_message_and_log(monkeypatch, caplog):
    secret = 'job68-env-credential'
    monkeypatch.setenv('FREECAD_MCP_SESSION_TOKEN', secret)
    error = json_rpc_error_from_result({'ok': False, 'error': 'ValueError: ' + secret})
    assert secret not in str(error)
    remote = JsonRpcRemoteError(-32000, 'ValueError: ' + secret, data={})
    def execute(*_):
        raise remote
    result = execute_code_operation(SimpleNamespace(execute_code=execute), True, 'pass')
    assert secret not in str(result)
    assert secret not in caplog.text


@pytest.mark.parametrize('code_text', ['X', '\x00', '\u2603', '\ud800'])
def test_remote_semantic_code_is_bounded_with_the_diagnostic_envelope(code_text):
    remote = JsonRpcRemoteError(-32000, 'bad value', data={'error_code': code_text * 100000})
    def execute(*_):
        raise remote
    result = execute_code_operation(SimpleNamespace(execute_code=execute), True, 'pass')
    assert isinstance(result.structuredContent['error_code'], str)
    assert len(result.structuredContent['error_code'].encode()) <= 2048
    assert len(str(result).encode()) <= 65536


def test_source_redaction_preserves_diagnostic_schema_keys_and_frame_metadata():
    error = json_rpc_error_from_result({
        'ok': False, 'error_code': 'GUI_DISPATCH_FAILED', 'error': 'undefined name',
        'traceback': {'exception_type': 'NameError', 'frames': [
            {'file': 'line_module.py', 'function': 'line', 'line': 17, 'code': 'line'}]}})
    frame = error['data']['traceback']['frames'][0]
    assert frame['line'] == 17
    assert frame['file'] == 'line_module.py'
    assert frame['function'] == 'line'
    assert frame['code'] == ''
    assert error['data']['error_code'] == 'GUI_DISPATCH_FAILED'


def test_total_budget_keeps_required_rpc_fields_and_semantic_code():
    import json
    def tree(depth):
        if depth == 0:
            return 'diagnostic value' * 1000
        return {'L' + 'x' * 120: tree(depth - 1), 'R' + 'x' * 120: tree(depth - 1)}
    error = json_rpc_error_from_result({
        'ok': False, 'error_code': 'DOCUMENT_CLOSE_REJECTED', 'error': 'bad value',
        'details': {'tree': tree(7)}})
    assert set(error) == {'code', 'message', 'data'}
    assert error['code'] == -32004
    assert isinstance(error['message'], str)
    assert error['data']['error_code'] == 'DOCUMENT_CLOSE_REJECTED'
    assert len(json.dumps(error).encode()) <= 32768


def test_gui_console_exception_diagnostic_scrubs_known_secret_and_bounds_size(monkeypatch):
    secret = 'job68-console-credential'
    monkeypatch.setenv('FREECAD_MCP_SESSION_TOKEN', secret)
    logged = []
    app = SimpleNamespace(Console=SimpleNamespace(
        PrintMessage=lambda _: None, PrintError=logged.append))
    ok, trace = run_python_on_gui_thread(
        f'raise ValueError({secret!r} + "!" * 100000)', io.StringIO(), freecad=app)
    assert not ok
    assert trace['exception_type'] == 'ValueError'
    assert trace['line_number'] == 1
    assert secret not in ''.join(logged)
    assert len(''.join(logged).encode()) <= 4096
