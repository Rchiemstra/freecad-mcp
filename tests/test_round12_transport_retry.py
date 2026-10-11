from http.client import RemoteDisconnected
from types import SimpleNamespace as NS
from unittest.mock import MagicMock
import pytest
from freecad_mcp.generated.capabilities.connection_methods.connection_invoke_v2_helpers import invoke_v2_transport
from freecad_mcp.freecad_client_ops.rpc_invocation_error import RpcInvocationError

pytestmark = pytest.mark.unit


def invoke(method, params, effects):
    conn = NS(invoke_rpc=MagicMock(side_effect=effects))
    context = NS(request_id='qa', to_envelope=lambda *a:{}, execution_category='public_execute_code')
    return conn, lambda: invoke_v2_transport(conn, method, params, context, control=False, timeout=5)


def test_successful_read_is_sent_once():
    conn, call = invoke('get_objects', {'doc_name':'Doc'}, [{'success':True}])
    assert call()['success']
    assert conn.invoke_rpc.call_count == 1


def test_dropped_read_retries_once():
    conn, call = invoke('get_objects', {'doc_name':'Doc'}, [RemoteDisconnected(), {'success':True}])
    assert call()['success']
    assert conn.invoke_rpc.call_count == 2


def test_mutation_is_never_retried():
    conn, call = invoke('edit_object', {'doc_name':'Doc'}, [RemoteDisconnected(), {'success':True}])
    with pytest.raises(RpcInvocationError):
        call()
    assert conn.invoke_rpc.call_count == 1


def test_second_drop_reports_live_freecad():
    conn, call = invoke('get_objects', {}, [RemoteDisconnected(), RemoteDisconnected(), True])
    with pytest.raises(RpcInvocationError, match='transport dropped; FreeCAD is still running'):
        call()
    assert conn.invoke_rpc.call_count == 3


def test_read_only_execute_retries_without_replaying_a_live_mutation():
    conn, call = invoke('execute_code', {'code':'print(1)', 'options':{'read_only':True}},
                        [RemoteDisconnected(), {'success':True}])
    assert call()['success']
    assert conn.invoke_rpc.call_count == 2


def test_report_clear_is_not_retried():
    conn, call = invoke('get_report_view', {'clear':True}, [RemoteDisconnected(), {'success':True}])
    with pytest.raises(RpcInvocationError):
        call()
    assert conn.invoke_rpc.call_count == 1


def test_recomputing_query_is_not_retried():
    conn, call = invoke('measure_distance', {'doc_name':'Doc'}, [RemoteDisconnected(), {'success':True}])
    with pytest.raises(RpcInvocationError):
        call()
    assert conn.invoke_rpc.call_count == 1
