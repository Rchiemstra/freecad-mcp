"""Late GUI completion must retain each public typed RPC response contract."""

import threading
from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import (
    execute_code,
    expressions,
    object_crud,
    sketch_public,
)
from addon.FreeCADMCP.rpc_server.methods.dispatch_helpers_ops.mutation_health import (
    adapt_gui_mutation_result,
)
from freecad_mcp.freecad_client import FreeCADConnection

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "module,method,args,raw,expected",
    [
        (
            object_crud,
            "create_object",
            ("Doc", {"Type": "App::Link", "Name": "Link"}),
            True,
            {"success": True, "object_name": "Link"},
        ),
        (
            object_crud,
            "edit_object",
            ("Doc", "Link", {"Properties": {}}),
            True,
            {"success": True, "object_name": "Link"},
        ),
        (
            sketch_public,
            "sketch_create",
            ("Doc", "Sketch"),
            True,
            {"success": True, "sketch_name": "Sketch"},
        ),
        (
            sketch_public,
            "sketch_add_geometry",
            ("Doc", "Sketch", []),
            [0, 1],
            {"success": True, "indices": [0, 1]},
        ),
        (
            sketch_public,
            "sketch_add_constraint",
            ("Doc", "Sketch", []),
            True,
            {"success": True},
        ),
        (
            sketch_public,
            "sketch_delete_constraint",
            ("Doc", "Sketch", [0]),
            True,
            {"success": True},
        ),
        (
            sketch_public,
            "sketch_delete_geometry",
            ("Doc", "Sketch", [0]),
            True,
            {"success": True},
        ),
        (
            sketch_public,
            "pad_feature",
            ("Doc", "Sketch", "Pad", 10.0),
            True,
            {"success": True, "pad_name": "Pad"},
        ),
        (
            sketch_public,
            "pocket_feature",
            ("Doc", "Sketch", "Pocket", 10.0),
            True,
            {"success": True, "pocket_name": "Pocket"},
        ),
        (
            expressions,
            "set_expression",
            ("Doc", "Pad", "Length", "missing.Value"),
            "invalid expression",
            {"success": False, "error": "invalid expression"},
        ),
        (
            expressions,
            "clear_expression",
            ("Doc", "Pad", "Length"),
            "missing object",
            {"success": False, "error": "missing object"},
        ),
    ],
)
def test_public_method_late_result_matches_normal_client_result(
    module, method, args, raw, expected
):
    transforms = []

    def dispatch(callback, *, late_result_transform=None):
        assert callable(late_result_transform), method
        transforms.append(late_result_transform)
        return raw

    facade = SimpleNamespace(
        _cad_collaborators=SimpleNamespace(),
        _dispatch_gui=dispatch,
        _adapt_gui_mutation_result=adapt_gui_mutation_result,
    )
    normal = getattr(module, method)(facade, *args)
    assert normal == expected
    assert len(transforms) == 1
    late = transforms[0](raw)
    connection = SimpleNamespace(_identity_lock=threading.Lock(), _rpc_session=None)
    recovered = FreeCADConnection._unwrap_v2_response(
        connection, {"ok": expected["success"], "late_completion": True, "result": late}
    )
    assert recovered == normal


@pytest.mark.parametrize(
    "raw",
    [
        {"ok": True, "stdout": "rectangle created", "session": {"geometry_count": 4}},
        {"ok": False, "error": "invalid constraint", "traceback": "failure traceback"},
        "GUI callback failed",
    ],
)
def test_generated_execute_late_result_retains_public_client_contract(raw):
    transforms = []

    def dispatch(callback, timeout, *, late_result_transform=None):
        assert timeout == 30.0
        assert callable(late_result_transform)
        transforms.append(late_result_transform)
        return raw

    def no_risk(*args, **kwargs):
        return None

    facade = SimpleNamespace(
        allow_execute_code=True,
        _execution_collaborators=SimpleNamespace(
            analyze_execute_code=lambda code, options: {"document_scope": ["Doc"]},
            typed_tool_warning=no_risk,
            find_modal_command_risk=no_risk,
            find_gui_geometry_loop_risk=no_risk,
            find_gui_blocking_risk=no_risk,
            execute_timeout=30.0,
        ),
        _dispatch_gui=dispatch,
    )
    normal = execute_code.execute_code(
        facade,
        "# generated rectangle operation",
        {"document": "Doc", "execution_mode": "gui", "generated_operation": True},
    )
    assert len(transforms) == 1
    late = transforms[0](raw)
    connection = SimpleNamespace(_identity_lock=threading.Lock(), _rpc_session=None)
    recovered = FreeCADConnection._unwrap_v2_response(
        connection, {"ok": late["success"], "late_completion": True, "result": late}
    )
    assert recovered == normal
    assert recovered["execution_category"] == "generated_internal_execute"
    if isinstance(raw, dict) and raw.get("ok"):
        assert recovered["success"] is True
        assert recovered["structured"] == {"geometry_count": 4}
        assert "rectangle created" in recovered["message"]
    else:
        assert recovered["success"] is False
        assert recovered["is_error"] is True
        assert "error" in recovered
