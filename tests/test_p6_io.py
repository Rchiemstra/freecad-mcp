"""
Tests for P6 import/export operations.

Layer-A: Schema / error propagation
Layer-B: Code-fragment and API-call checks
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from mcp.types import TextContent

from freecad_mcp._shared.protocol.export_brep_contract import (
    make_export_brep_failure,
    make_export_brep_success,
)
from freecad_mcp._shared.protocol.export_step_contract import (
    make_export_step_failure,
    make_export_step_success,
)
from freecad_mcp._shared.protocol.export_stl_contract import (
    make_export_stl_failure,
    make_export_stl_success,
)
from freecad_mcp._shared.protocol.import_brep_contract import (
    make_import_brep_failure,
    make_import_brep_success,
)
from freecad_mcp._shared.protocol.import_step_contract import (
    make_import_step_failure,
    make_import_step_success,
)
from freecad_mcp.operations.p6_io import (
    export_brep_operation,
    export_step_operation,
    export_stl_operation,
    import_brep_operation,
    import_step_operation,
    set_color_operation,
)
from tests.helpers.geometric import assert_code_compiles, assert_code_contains


_MEASURE_IO = (
    Path(__file__).resolve().parents[1]
    / "addon"
    / "FreeCADMCP"
    / "rpc_server"
    / "methods"
    / "cad_methods_ops"
    / "measure_io_actions.py"
).read_text(encoding="utf-8")


def _ok_conn():
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
    conn.execute_code.return_value = {"success": True, "message": "done", "recompute_errors": []}
    conn.export_step.return_value = make_export_step_success("/tmp/out.step", 1)
    conn.export_stl.return_value = make_export_stl_success("/tmp/out.stl", 1, 12)
    conn.export_brep.return_value = make_export_brep_success("/tmp/out.brep", True, "Obj1")
    conn.import_step.return_value = make_import_step_success("/tmp/in.step", True)
    conn.import_brep.return_value = make_import_brep_success("/tmp/in.brep", "BRepImport", True)
    return conn


def _fail_conn():
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
    conn.execute_code.return_value = {"success": False, "error": "oops"}
    conn.export_step.return_value = make_export_step_failure("EXPORT_STEP_FAILED", "oops")
    conn.export_stl.return_value = make_export_stl_failure("EXPORT_STL_FAILED", "oops")
    conn.export_brep.return_value = make_export_brep_failure("EXPORT_BREP_FAILED", "oops")
    conn.import_step.return_value = make_import_step_failure("IMPORT_STEP_FAILED", "oops")
    conn.import_brep.return_value = make_import_brep_failure("IMPORT_BREP_FAILED", "oops")
    return conn


def _code(conn) -> str:
    return conn.execute_code.call_args[0][0]


def _text(response) -> str:
    content = response.content if hasattr(response, "content") else response
    return " ".join(item.text for item in content if isinstance(item, TextContent))


def _assert_native_export(conn: MagicMock, method: str) -> None:
    getattr(conn, method).assert_called_once()
    conn.execute_code.assert_not_called()
    assert ".recompute(" not in _MEASURE_IO


# ---------------------------------------------------------------------------
# P6-1  export_step
# ---------------------------------------------------------------------------

class TestExportStep:
    def test_success(self):
        resp = export_step_operation(_ok_conn(), "Doc", "/tmp/out.step")
        assert _text(resp)

    def test_failure(self):
        resp = export_step_operation(_fail_conn(), "Doc", "/tmp/out.step")
        assert "oops" in _text(resp) or "Failed" in _text(resp)

    def test_compiles(self):
        assert_code_compiles(_MEASURE_IO)

    def test_import_Import_called(self):
        assert_code_contains(_MEASURE_IO, 'load_module("Import")')

    def test_export_called(self):
        assert_code_contains(_MEASURE_IO, '"export"')

    def test_path_in_rpc(self):
        conn = _ok_conn()
        export_step_operation(conn, "Doc", "/my/path/gear.step")
        conn.export_step.assert_called_once_with("Doc", "/my/path/gear.step", None)

    def test_obj_names_filter(self):
        conn = _ok_conn()
        export_step_operation(conn, "Doc", "/tmp/out.step", obj_names=["Pad", "Fillet"])
        conn.export_step.assert_called_once_with("Doc", "/tmp/out.step", ["Pad", "Fillet"])

    def test_native_txn_without_apply_recompute(self):
        conn = _ok_conn()
        export_step_operation(conn, "Doc", "/tmp/out.step")
        _assert_native_export(conn, "export_step")


# ---------------------------------------------------------------------------
# P6-2  import_step
# ---------------------------------------------------------------------------

class TestImportStep:
    def test_success(self):
        resp = import_step_operation(_ok_conn(), "Doc", "/tmp/in.step")
        assert _text(resp)

    def test_compiles(self):
        assert_code_compiles(_MEASURE_IO)

    def test_insert_called(self):
        assert_code_contains(_MEASURE_IO, '"insert"')

    def test_path_in_rpc(self):
        conn = _ok_conn()
        import_step_operation(conn, "Doc", "/data/part.step")
        conn.import_step.assert_called_once_with("Doc", "/data/part.step")

    def test_apply_does_not_recompute(self):
        conn = _ok_conn()
        import_step_operation(conn, "Doc", "/tmp/in.step")
        conn.import_step.assert_called_once()
        conn.execute_code.assert_not_called()
        assert ".recompute(" not in _MEASURE_IO


# ---------------------------------------------------------------------------
# P6-3  export_stl
# ---------------------------------------------------------------------------

class TestExportStl:
    def test_success(self):
        resp = export_stl_operation(_ok_conn(), "Doc", "/tmp/out.stl")
        assert _text(resp)

    def test_compiles(self):
        assert_code_compiles(_MEASURE_IO)

    def test_mesh_module_used(self):
        assert_code_contains(_MEASURE_IO, 'load_module("Mesh")')

    def test_tessellate_called(self):
        assert_code_contains(_MEASURE_IO, "tessellate")

    def test_deviation_in_rpc(self):
        conn = _ok_conn()
        export_stl_operation(conn, "Doc", "/tmp/out.stl", mesh_deviation=0.05)
        conn.export_stl.assert_called_once_with("Doc", "/tmp/out.stl", None, 0.05)

    def test_obj_names_filter(self):
        conn = _ok_conn()
        export_stl_operation(conn, "Doc", "/tmp/out.stl", obj_names=["Pad1"])
        conn.export_stl.assert_called_once_with("Doc", "/tmp/out.stl", ["Pad1"], 0.1)

    def test_native_txn_without_apply_recompute(self):
        conn = _ok_conn()
        export_stl_operation(conn, "Doc", "/tmp/out.stl")
        _assert_native_export(conn, "export_stl")


# ---------------------------------------------------------------------------
# P6-4  export_brep
# ---------------------------------------------------------------------------

class TestExportBrep:
    def test_success(self):
        resp = export_brep_operation(_ok_conn(), "Doc", "Obj1", "/tmp/out.brep")
        assert _text(resp)

    def test_compiles(self):
        assert_code_compiles(_MEASURE_IO)

    def test_exportBrep_called(self):
        assert_code_contains(_MEASURE_IO, "exportBrep")

    def test_path_in_rpc(self):
        conn = _ok_conn()
        export_brep_operation(conn, "Doc", "Obj1", "/data/shape.brep")
        conn.export_brep.assert_called_once_with("Doc", "Obj1", "/data/shape.brep")

    def test_native_txn_without_apply_recompute(self):
        conn = _ok_conn()
        export_brep_operation(conn, "Doc", "Obj1", "/tmp/out.brep")
        _assert_native_export(conn, "export_brep")


# ---------------------------------------------------------------------------
# P6-5  import_brep
# ---------------------------------------------------------------------------

class TestImportBrep:
    def test_success(self):
        resp = import_brep_operation(_ok_conn(), "Doc", "/tmp/in.brep")
        assert _text(resp)

    def test_compiles(self):
        assert_code_compiles(_MEASURE_IO)

    def test_importBrep_called(self):
        assert_code_contains(_MEASURE_IO, "importBrep")

    def test_path_in_rpc(self):
        conn = _ok_conn()
        import_brep_operation(conn, "Doc", "/data/body.brep")
        conn.import_brep.assert_called_once_with("Doc", "/data/body.brep", "BRepImport")

    def test_obj_name_default(self):
        conn = _ok_conn()
        import_brep_operation(conn, "Doc", "/tmp/in.brep")
        conn.import_brep.assert_called_once_with("Doc", "/tmp/in.brep", "BRepImport")

    def test_obj_name_custom(self):
        conn = _ok_conn()
        import_brep_operation(conn, "Doc", "/tmp/in.brep", obj_name="MyShape")
        conn.import_brep.assert_called_once_with("Doc", "/tmp/in.brep", "MyShape")


# ---------------------------------------------------------------------------
# P6-6  set_color
# ---------------------------------------------------------------------------

class TestSetColor:
    def test_success(self):
        resp = set_color_operation(_ok_conn(), True, "Doc", "Obj1", 1.0, 0.0, 0.0)
        assert _text(resp)

    def test_compiles(self):
        conn = _ok_conn()
        set_color_operation(conn, True, "Doc", "Obj1", 0.5, 0.5, 0.5)
        assert_code_compiles(_code(conn))

    def test_ShapeColor_set(self):
        conn = _ok_conn()
        set_color_operation(conn, True, "Doc", "Obj1", 1.0, 0.0, 0.0)
        assert_code_contains(_code(conn), "ShapeColor")

    def test_rgb_values_in_code(self):
        conn = _ok_conn()
        set_color_operation(conn, True, "Doc", "Obj1", 0.2, 0.6, 0.8)
        code = _code(conn)
        assert_code_contains(code, "0.2", "0.6", "0.8")

    def test_transparency_in_code(self):
        conn = _ok_conn()
        set_color_operation(conn, True, "Doc", "Obj1", 1.0, 1.0, 1.0, transparency=0.5)
        assert_code_contains(_code(conn), "Transparency")

    def test_object_name_in_code(self):
        conn = _ok_conn()
        set_color_operation(conn, True, "Doc", "RedPart", 1.0, 0.0, 0.0)
        assert_code_contains(_code(conn), "RedPart")
