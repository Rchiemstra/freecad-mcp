from http.client import RemoteDisconnected
import json
from types import SimpleNamespace as NS
import pytest
from freecad_mcp.freecad_client_ops.proxy_lane import ProxyLane

pytestmark = pytest.mark.unit


def lane(drop):
    calls = []
    def request(path, body, headers):
        calls.append(json.loads(body))
        if len(calls) <= drop:
            raise RemoteDisconnected()
        return 200, {'x-freecad-mcp-protocol':('jsonrpc-2.0',)}, json.dumps({
            'jsonrpc':'2.0','id':calls[-1]['id'],'result':True}).encode()
    proxy = ProxyLane('http://localhost:9875', 5, lambda *args:(), transport=NS(request=request, extra_headers=[]))
    return proxy, calls


def test_direct_read_success():
    proxy, calls = lane(0)
    assert proxy.call('list_documents') is True
    assert len(calls) == 1


def test_direct_read_drop_retries():
    proxy, calls = lane(1)
    assert proxy.call('list_documents') is True
    assert len(calls) == 2


def test_direct_mutation_drop_is_not_retried():
    proxy, calls = lane(1)
    with pytest.raises(RemoteDisconnected):
        proxy.call('create_document', 'X')
    assert len(calls) == 1


def test_second_drop_reports_live_server():
    from freecad_mcp.freecad_client_ops.rpc_invocation_error import RpcInvocationError
    proxy, calls = lane(2)
    with pytest.raises(RpcInvocationError, match='transport dropped; FreeCAD is still running'):
        proxy.call('list_documents')
    assert [call['method'] for call in calls] == ['list_documents','list_documents','ping']


def test_direct_report_clear_is_not_retried():
    proxy, calls = lane(1)
    with pytest.raises(RemoteDisconnected):
        proxy.call('get_report_view', 200, True)
    assert len(calls) == 1
