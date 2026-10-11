"""One dropped-connection retry, limited to requests without live side effects."""
from __future__ import annotations

import json
from functools import lru_cache
from http.client import IncompleteRead, RemoteDisconnected
from pathlib import Path

_DROPPED = (RemoteDisconnected, IncompleteRead, ConnectionResetError, BrokenPipeError, EOFError)


@lru_cache(maxsize=1)
def _pure_reads() -> frozenset[str]:
    path = Path(__file__).resolve().parents[1] / 'generated/capabilities/gateway_dispatch.json'
    entries = json.loads(path.read_text())['entries']
    # Many query handlers recompute, which can execute feature code. Audit a
    # handler before admitting it here; read metadata alone is insufficient.
    pure = {
        'geometric_diff', 'inspect_references', 'compare_documents',
        'get_mutation_readiness', 'check_gear_pair', 'compute_gear_geometry',
        'get_object', 'get_objects', 'get_parts_list', 'list_documents',
        'get_gui_state', 'get_report_view', 'get_selection', 'check_rpc_sync',
        'get_request_status', 'get_runtime_info', 'get_worker_status',
    }
    return (frozenset(e['rpc_method'] for e in entries if e['mutation_class'] == 'read') & pure) | {
        'get_instance_info', 'get_rpc_method_capabilities',
        'spreadsheet_get_cells', 'spreadsheet_list_aliases',
    }



def retry_safe_read(method, params) -> bool:
    if method == 'execute_code':
        return (params or {}).get('options', {}).get('read_only') is True
    if method == 'get_report_view' and (params or {}).get('clear'):
        return False
    return method in _pure_reads()


def invoke_with_read_retry(conn, method, params, transport_method, envelope, *, control, timeout):
    def send():
        return conn.invoke_rpc(transport_method, envelope, control=control, timeout=timeout)
    try:
        return send()
    except _DROPPED:
        if not retry_safe_read(method, params):
            raise
    try:
        return send()
    except _DROPPED as exc:
        alive = False
        try:
            alive = conn.invoke_rpc('ping', control=True, timeout=3) is True
        except Exception:
            pass
        if alive:
            from .rpc_invocation_error import RpcInvocationError
            raise RpcInvocationError(method, exc, freecad_alive=True) from None
        raise


def invoke_direct_read_retry(lane, method, args, send, *, notification=False):
    try:
        return send()
    except _DROPPED:
        params = {'clear': args[1]} if method == 'get_report_view' and len(args) > 1 else {}
        if notification or not retry_safe_read(method, params):
            raise
    try:
        return send()
    except _DROPPED as exc:
        try:
            alive = lane.call('ping') is True
        except Exception:
            alive = False
        if alive:
            from .rpc_invocation_error import RpcInvocationError
            raise RpcInvocationError(method, exc, freecad_alive=True) from None
        raise
