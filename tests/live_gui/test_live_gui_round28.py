"""Round 28: named sketch constraints survive external source close/reopen."""
import pytest

from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round5 import _payload
from tests.live_gui.test_live_gui_round23 import _pad

pytestmark = pytest.mark.live_gui


def _setup(mcp, live_gui, opened):
    for doc in ("SrcDoc", "DepDoc"):
        assert_ok(mcp.call("create_document", name=doc))
        opened.append(doc)
    assert_ok(mcp.call("spreadsheet_create", doc_name="SrcDoc", sheet_name="Dims"))
    assert_ok(mcp.call("spreadsheet_set_cells", doc_name="SrcDoc", sheet_name="Dims", cells=[
        {"address": "A1", "value": 12, "alias": "PadLen"},
        {"address": "A2", "value": 30, "alias": "Wall"},
    ]))
    for doc, width, height in (("SrcDoc", 40, 20), ("DepDoc", 30, 15)):
        _pad(mcp, doc, "Body", "Sketch", "Pad", width, height)
        # sketch_add_rectangle supplies the four corner coincidences.
        constraints = [
            {"type": "Horizontal", "geo": 0}, {"type": "Horizontal", "geo": 2},
            {"type": "Vertical", "geo": 1}, {"type": "Vertical", "geo": 3},
            {"type": "Distance", "geo": 0, "value": width, "name": "W"},
            {"type": "Distance", "geo": 1, "value": height, "name": "H"},
            {"type": "Coincident", "geo1": 0, "pos1": 1, "geo2": -1, "pos2": 1},
        ]
        assert_ok(mcp.call("sketch_add_constraint", doc_name=doc, sketch_name="Sketch", constraints=constraints))
        assert_ok(mcp.call("save_document_as", selector={"document_name": doc},
                           destination=str(live_gui.workdir / (doc + ".FCStd")), overwrite=True))
    for doc, expression in (("SrcDoc", "<<Dims>>.PadLen"), ("DepDoc", "SrcDoc#<<Dims>>.PadLen")):
        assert_ok(mcp.call("set_expression", doc_name=doc, object_name="Pad", prop_path="Length", expression=expression))
    for path, alias in (("Constraints[8]", "Wall"), ("Constraints.H", "PadLen")):
        assert_ok(mcp.call("set_expression", doc_name="DepDoc", object_name="Sketch",
                           prop_path=path, expression="SrcDoc#<<Dims>>." + alias))
    for doc in opened:
        assert_ok(mcp.call("save_document", selector={"document_name": doc}))


def _width(mcp, expected):
    result = _payload(assert_ok(mcp.call("execute_code", document="DepDoc", recompute="none",
        code="sk = FreeCAD.getDocument('DepDoc').Sketch\nassert abs(sk.getDatum(8).Value - %s) < 1e-7, sk.getDatum(8)" % expected)))
    return result


@pytest.mark.parametrize("mode", ["open", "reopen", "closed"],
                         ids=["happy_open", "defect_reopened", "defect_clear_closed"])
def test_round28_constraint_source_lifecycle(mcp, gui_log, live_gui, mode):
    opened = []
    try:
        _setup(mcp, live_gui, opened)
        if mode == "closed":
            # Isolate closed-source sketch repair from the Pad's independent
            # missing Length binding. The reopen case retains the exact repro.
            assert_ok(mcp.call("clear_expression", doc_name="DepDoc", object_name="Pad", prop_path="Length"))
        if mode != "open":
            assert_ok(mcp.call("close_document", doc_name="SrcDoc"))
            opened.remove("SrcDoc")
        if mode == "reopen":
            assert_ok(mcp.call("open_document", path=str(live_gui.workdir / "SrcDoc.FCStd")))
            opened.append("SrcDoc")
            diagnosis = _payload(assert_ok(mcp.call("diagnose_parametric", doc_name="DepDoc")))
            assert not diagnosis["expression_issues"], diagnosis
            assert not diagnosis["invalid_objects"], diagnosis
            _width(mcp, 30)
            assert_ok(mcp.call("spreadsheet_set_cells", doc_name="SrcDoc", sheet_name="Dims",
                               cells=[{"address": "A2", "value": 42}]))
            assert_ok(mcp.call("recompute_document", doc_name="DepDoc"))
            _width(mcp, 42)
        if mode != "closed":
            diagnosis = _payload(assert_ok(mcp.call("diagnose_parametric", doc_name="DepDoc")))
            assert not diagnosis["expression_issues"], diagnosis
            assert not diagnosis["invalid_objects"], diagnosis
        # W and H share a property. Clearing W must work while H is unresolved,
        # and one undo must restore W without changing H.
        assert_ok(mcp.call("clear_expression", doc_name="DepDoc", object_name="Sketch", prop_path="Constraints.W"))
        assert_ok(mcp.call("undo", doc_name="DepDoc"))
        bindings = _payload(assert_ok(mcp.call("list_expressions", doc_name="DepDoc", object_name="Sketch")))
        assert bindings["count"] == 2 and "Constraints.W" in str(bindings) and "Constraints.H" in str(bindings), bindings
        if mode == "closed":
            # Undo leaves closed-source recompute work; clear is the repair path.
            assert_ok(mcp.call("clear_expression", doc_name="DepDoc", object_name="Sketch", prop_path="Constraints.W"))
        else:
            assert_ok(mcp.call("redo", doc_name="DepDoc"))
        if mode == "closed":
            # The retained H binding must reattach after the partial repair.
            assert_ok(mcp.call("open_document", path=str(live_gui.workdir / "SrcDoc.FCStd")))
            opened.append("SrcDoc")
            assert_ok(mcp.call("recompute_document", doc_name="DepDoc"))
            assert_ok(mcp.call("spreadsheet_set_cells", doc_name="SrcDoc", sheet_name="Dims",
                               cells=[{"address": "A1", "value": 18}]))
            assert_ok(mcp.call("recompute_document", doc_name="DepDoc"))
            assert_ok(mcp.call("execute_code", document="DepDoc", recompute="none",
                code="assert abs(FreeCAD.getDocument('DepDoc').Sketch.getDatum(9).Value - 18) < 1e-7"))
            assert_ok(mcp.call("close_document", doc_name="SrcDoc"))
            opened.remove("SrcDoc")
        assert_ok(mcp.call("clear_expression", doc_name="DepDoc", object_name="Sketch", prop_path="Constraints.H"))
        assert_ok(mcp.call("sketch_edit_constraint", doc_name="DepDoc", sketch_name="Sketch", index=8, value=35))
        _width(mcp, 35)
    finally:
        for doc in reversed(opened):
            assert_ok(mcp.call("close_document", doc_name=doc))
    assert_clean(gui_log, r".*(not found|failed to recompute|unresolved cross-document|Error in expression|document recompute).*")
