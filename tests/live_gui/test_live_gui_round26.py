"""Round 26: prepared object Label writes retain native rename semantics."""
import pytest

from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round5 import _payload

pytestmark = pytest.mark.live_gui


def _label(mcp, doc, obj):
    return _payload(assert_ok(mcp.call("get_object", doc_name=doc, obj_name=obj)))


@pytest.mark.parametrize("kind", ["Spreadsheet::Sheet", "Part::Box", "App::Part", "PartDesign::Body", "Sketcher::SketchObject"])
@pytest.mark.parametrize("mode", ["typed", "gui"])
def test_round26_fresh_object_label(mcp, gui_log, kind, mode):
    doc, obj = "SrcDoc", "Dims"
    assert_ok(mcp.call("create_document", name=doc))
    try:
        if kind == "Spreadsheet::Sheet":
            assert_ok(mcp.call("spreadsheet_create", doc_name=doc, sheet_name=obj))
        else:
            assert_ok(mcp.call("create_object", doc_name=doc, obj_name=obj, obj_type=kind))
        if mode == "typed":
            result = mcp.call("edit_object", doc_name=doc, obj_name=obj,
                              obj_properties={"Label": "DimsRenamed"})
        else:
            result = mcp.call("execute_code", document=doc, recompute="none", execution_mode="gui",
                              code="import FreeCAD\nFreeCAD.getDocument('SrcDoc').getObject('Dims').Label='DimsRenamed'")
        assert_ok(result)
        assert "DimsRenamed" in str(_label(mcp, doc, obj))
        assert_ok(mcp.call("undo", doc_name=doc))
        assert "DimsRenamed" not in str(_label(mcp, doc, obj))
        assert_ok(mcp.call("redo", doc_name=doc))
        assert "DimsRenamed" in str(_label(mcp, doc, obj))
    finally:
        assert_ok(mcp.call("close_document", doc_name=doc))
    assert_clean(gui_log)


@pytest.mark.parametrize("cross_document", [False, True], ids=["local", "saved_external"])
@pytest.mark.parametrize("mode", ["typed", "gui"])
def test_round26_label_expression(mcp, gui_log, live_gui, cross_document, mode):
    opened = ["SrcDoc"]
    assert_ok(mcp.call("create_document", name="SrcDoc"))
    try:
        assert_ok(mcp.call("spreadsheet_create", doc_name="SrcDoc", sheet_name="Dims"))
        assert_ok(mcp.call("spreadsheet_set_cells", doc_name="SrcDoc", sheet_name="Dims",
                           cells=[{"address": "A1", "value": 12, "alias": "Size"}]))
        dep = "DepDoc" if cross_document else "SrcDoc"
        if cross_document:
            assert_ok(mcp.call("create_document", name=dep))
            opened.append(dep)
        assert_ok(mcp.call("create_object", doc_name=dep, obj_name="Box", obj_type="Part::Box"))
        assert_ok(mcp.call("spreadsheet_create", doc_name=dep, sheet_name="Bridge"))
        for doc in opened:
            assert_ok(mcp.call("save_document_as", selector={"document_name": doc},
                               destination=str(live_gui.workdir / (doc + ".FCStd")), overwrite=True))
        prefix = "SrcDoc#" if cross_document else ""
        assert_ok(mcp.call("set_expression", doc_name=dep, object_name="Box", prop_path="Length",
                           expression=prefix + "<<Dims>>.Size"))
        assert_ok(mcp.call("spreadsheet_set_cells", doc_name=dep, sheet_name="Bridge",
                           cells=[{"address": "A1", "value": "=" + prefix + "<<Dims>>.Size"}]))
        for doc in opened:
            assert_ok(mcp.call("save_document_as", selector={"document_name": doc},
                               destination=str(live_gui.workdir / (doc + ".FCStd")), overwrite=True))
        if mode == "typed":
            assert_ok(mcp.call("edit_object", doc_name="SrcDoc", obj_name="Dims",
                               obj_properties={"Label": "DimsRenamed"}))
        else:
            assert_ok(mcp.call("execute_code", document="SrcDoc", recompute="none", execution_mode="gui",
                               code="import FreeCAD\nFreeCAD.getDocument('SrcDoc').getObject('Dims').Label='DimsRenamed'"))
        expressions = _payload(assert_ok(mcp.call("list_expressions", doc_name=dep, object_name="Box")))
        assert "<<DimsRenamed>>.Size" in str(expressions), expressions
        cells = _payload(assert_ok(mcp.call("spreadsheet_get_cells", doc_name=dep,
                                           sheet_name="Bridge", addresses=["A1"])))
        assert "DimsRenamed" in str(cells), cells
        if not cross_document:
            assert_ok(mcp.call("undo", doc_name="SrcDoc"))
            expressions = _payload(assert_ok(mcp.call("list_expressions", doc_name=dep, object_name="Box")))
            assert "<<Dims>>.Size" in str(expressions), expressions
            assert_ok(mcp.call("redo", doc_name="SrcDoc"))
            expressions = _payload(assert_ok(mcp.call("list_expressions", doc_name=dep, object_name="Box")))
            assert "<<DimsRenamed>>.Size" in str(expressions), expressions
        assert_ok(mcp.call("spreadsheet_set_cells", doc_name="SrcDoc", sheet_name="Dims",
                           cells=[{"address": "A1", "value": 18}]))
        assert_ok(mcp.call("recompute_document", doc_name=dep))
        cells = _payload(assert_ok(mcp.call("spreadsheet_get_cells", doc_name=dep,
                                           sheet_name="Bridge", addresses=["A1"])))
        assert float(cells["cells"][0]["value"]) == pytest.approx(18), cells
    finally:
        for doc in reversed(opened):
            assert_ok(mcp.call("close_document", doc_name=doc))
    assert_clean(gui_log)


@pytest.mark.parametrize("kind", ["Part::Box", "App::Part", "PartDesign::Body", "Sketcher::SketchObject"])
@pytest.mark.parametrize("mode", ["typed", "gui"])
def test_round26_other_object_label_reference(mcp, gui_log, kind, mode):
    assert_ok(mcp.call("create_document", name="SrcDoc"))
    try:
        assert_ok(mcp.call("create_object", doc_name="SrcDoc", obj_name="Dims", obj_type=kind))
        assert_ok(mcp.call("create_object", doc_name="SrcDoc", obj_name="Dependent", obj_type="Part::Box"))
        assert_ok(mcp.call("set_expression", doc_name="SrcDoc", object_name="Dependent", prop_path="Length",
                           expression="<<Dims>>.Placement.Base.x + 12 mm"))
        if mode == "typed":
            assert_ok(mcp.call("edit_object", doc_name="SrcDoc", obj_name="Dims",
                               obj_properties={"Label": "DimsRenamed"}))
        else:
            assert_ok(mcp.call("execute_code", document="SrcDoc", recompute="none", execution_mode="gui",
                               code="import FreeCAD\nFreeCAD.getDocument('SrcDoc').getObject('Dims').Label='DimsRenamed'"))
        for action, label in ((None, "DimsRenamed"), ("undo", "Dims"), ("redo", "DimsRenamed")):
            if action:
                assert_ok(mcp.call(action, doc_name="SrcDoc"))
            expressions = _payload(assert_ok(mcp.call("list_expressions", doc_name="SrcDoc",
                                                      object_name="Dependent")))
            assert "<<" + label + ">>.Placement.Base.x" in str(expressions), expressions
    finally:
        assert_ok(mcp.call("close_document", doc_name="SrcDoc"))
    assert_clean(gui_log)
