"""
Tests for P6 import/export operations.

Layer-A: Schema / error propagation
Layer-B: Code-fragment and API-call checks
"""
from __future__ import annotations

from unittest.mock import MagicMock

from mcp.types import TextContent

from freecad_mcp.operations.p6_io import (
    export_brep_operation,
    export_step_operation,
    export_stl_operation,
    import_brep_operation,
    import_step_operation,
    set_color_operation,
)
from tests.helpers.geometric import assert_code_compiles, assert_code_contains


def _ok_conn():
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
    conn.execute_code.return_value = {"success": True, "message": "done", "recompute_errors": []}
    return conn


def _fail_conn():
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
    conn.execute_code.return_value = {"success": False, "error": "oops"}
    return conn


def _code(conn) -> str:
    return conn.execute_code.call_args[0][0]


def _text(response) -> str:
    return " ".join(item.text for item in response if isinstance(item, TextContent))


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
        conn = _ok_conn()
        export_step_operation(conn, "Doc", "/tmp/out.step")
        assert_code_compiles(_code(conn))

    def test_import_Import_called(self):
        conn = _ok_conn()
        export_step_operation(conn, "Doc", "/tmp/out.step")
        assert_code_contains(_code(conn), "import Import")

    def test_export_called(self):
        conn = _ok_conn()
        export_step_operation(conn, "Doc", "/tmp/out.step")
        assert_code_contains(_code(conn), "Import.export")

    def test_path_in_code(self):
        conn = _ok_conn()
        export_step_operation(conn, "Doc", "/my/path/gear.step")
        assert_code_contains(_code(conn), "/my/path/gear.step")

    def test_obj_names_filter(self):
        conn = _ok_conn()
        export_step_operation(conn, "Doc", "/tmp/out.step", obj_names=["Pad", "Fillet"])
        code = _code(conn)
        assert_code_contains(code, "Pad", "Fillet")


# ---------------------------------------------------------------------------
# P6-2  import_step
# ---------------------------------------------------------------------------

class TestImportStep:
    def test_success(self):
        resp = import_step_operation(_ok_conn(), "Doc", "/tmp/in.step")
        assert _text(resp)

    def test_compiles(self):
        conn = _ok_conn()
        import_step_operation(conn, "Doc", "/tmp/in.step")
        assert_code_compiles(_code(conn))

    def test_insert_called(self):
        conn = _ok_conn()
        import_step_operation(conn, "Doc", "/tmp/in.step")
        assert_code_contains(_code(conn), "Import.insert")

    def test_path_in_code(self):
        conn = _ok_conn()
        import_step_operation(conn, "Doc", "/data/part.step")
        assert_code_contains(_code(conn), "/data/part.step")

    def test_recompute_called(self):
        conn = _ok_conn()
        import_step_operation(conn, "Doc", "/tmp/in.step")
        assert_code_contains(_code(conn), "_doc.recompute()")


# ---------------------------------------------------------------------------
# P6-3  export_stl
# ---------------------------------------------------------------------------

class TestExportStl:
    def test_success(self):
        resp = export_stl_operation(_ok_conn(), "Doc", "/tmp/out.stl")
        assert _text(resp)

    def test_compiles(self):
        conn = _ok_conn()
        export_stl_operation(conn, "Doc", "/tmp/out.stl")
        assert_code_compiles(_code(conn))

    def test_mesh_module_used(self):
        conn = _ok_conn()
        export_stl_operation(conn, "Doc", "/tmp/out.stl")
        assert_code_contains(_code(conn), "import Mesh")

    def test_tessellate_called(self):
        conn = _ok_conn()
        export_stl_operation(conn, "Doc", "/tmp/out.stl")
        assert_code_contains(_code(conn), "tessellate")

    def test_deviation_in_code(self):
        conn = _ok_conn()
        export_stl_operation(conn, "Doc", "/tmp/out.stl", mesh_deviation=0.05)
        assert_code_contains(_code(conn), "0.05")

    def test_obj_names_filter(self):
        conn = _ok_conn()
        export_stl_operation(conn, "Doc", "/tmp/out.stl", obj_names=["Pad1"])
        assert_code_contains(_code(conn), "Pad1")


# ---------------------------------------------------------------------------
# P6-4  export_brep
# ---------------------------------------------------------------------------

class TestExportBrep:
    def test_success(self):
        resp = export_brep_operation(_ok_conn(), "Doc", "Obj1", "/tmp/out.brep")
        assert _text(resp)

    def test_compiles(self):
        conn = _ok_conn()
        export_brep_operation(conn, "Doc", "Obj1", "/tmp/out.brep")
        assert_code_compiles(_code(conn))

    def test_exportBrep_called(self):
        conn = _ok_conn()
        export_brep_operation(conn, "Doc", "Obj1", "/tmp/out.brep")
        assert_code_contains(_code(conn), "exportBrep")

    def test_path_in_code(self):
        conn = _ok_conn()
        export_brep_operation(conn, "Doc", "Obj1", "/data/shape.brep")
        assert_code_contains(_code(conn), "/data/shape.brep")


# ---------------------------------------------------------------------------
# P6-5  import_brep
# ---------------------------------------------------------------------------

class TestImportBrep:
    def test_success(self):
        resp = import_brep_operation(_ok_conn(), "Doc", "/tmp/in.brep")
        assert _text(resp)

    def test_compiles(self):
        conn = _ok_conn()
        import_brep_operation(conn, "Doc", "/tmp/in.brep")
        assert_code_compiles(_code(conn))

    def test_importBrep_called(self):
        conn = _ok_conn()
        import_brep_operation(conn, "Doc", "/tmp/in.brep")
        assert_code_contains(_code(conn), "importBrep")

    def test_path_in_code(self):
        conn = _ok_conn()
        import_brep_operation(conn, "Doc", "/data/body.brep")
        assert_code_contains(_code(conn), "/data/body.brep")

    def test_obj_name_default(self):
        conn = _ok_conn()
        import_brep_operation(conn, "Doc", "/tmp/in.brep")
        assert_code_contains(_code(conn), "BRepImport")

    def test_obj_name_custom(self):
        conn = _ok_conn()
        import_brep_operation(conn, "Doc", "/tmp/in.brep", obj_name="MyShape")
        assert_code_contains(_code(conn), "MyShape")


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
