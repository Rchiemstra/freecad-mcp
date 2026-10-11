import pytest
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.execute_code_response import finalize_gui_execute_response

pytestmark = pytest.mark.unit


def test_other_python_error_is_preserved():
    res = finalize_gui_execute_response(lambda v:v, {'ok':False,'error':'qa boom'}, {})
    assert res['error'] == 'qa boom'


def test_lifecycle_error_names_tools():
    res = finalize_gui_execute_response(lambda v:v, {'ok':False,'error':"document lifecycle changes are unavailable during the prepared commit for document 'X'"}, {'document':'X'})
    assert 'create_document' in res['error'] and 'open_document' in res['error']
