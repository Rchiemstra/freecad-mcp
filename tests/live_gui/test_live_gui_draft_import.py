"""Round 14 Draft API imports on the document owner thread."""
from __future__ import annotations

import pytest

from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round5 import _payload

pytestmark = pytest.mark.live_gui


def test_draft_hatch_import_freecad_tests(mcp, gui_log):
    assert_ok(mcp.call("create_document", name="R14DraftCore"))
    code = """import importlib.util, unittest, io
spec=importlib.util.spec_from_file_location('r14_import_gui', '/workspace/src/Mod/Draft/drafttests/test_import_gui.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
output=io.StringIO()
result=unittest.TextTestRunner(stream=output, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(module.DraftHatchImportIsolation))
assert result.wasSuccessful(), output.getvalue()
print(output.getvalue())
"""
    assert_ok(mcp.call("execute_code", document="R14DraftCore", execution_mode="gui", recompute="none", code=code))
    assert_ok(mcp.call("close_document", doc_name="R14DraftCore"))
    assert_clean(gui_log)


def test_draft_factory_import_and_rectangle(mcp, gui_log):
    doc = "R14DraftFactory"
    assert_ok(mcp.call("create_document", name=doc))
    result = assert_ok(mcp.call("execute_code", document=doc, execution_mode="gui", recompute="target",
                               code="import Draft\nrect=Draft.make_rectangle(20,10)\nprint(rect.Name)"))
    assert "Rectangle" in result.text
    area = _payload(assert_ok(mcp.call("measure_area", doc_name=doc, obj_name="Rectangle")))
    assert area["area_mm2"] == pytest.approx(200)
    assert_ok(mcp.call("close_document", doc_name=doc))
    assert_clean(gui_log)


def test_draft_pseudo_type_has_actionable_rejection(mcp, gui_log):
    doc = "R14DraftType"
    assert_ok(mcp.call("create_document", name=doc))
    # Ordinary document object creation remains usable.
    assert_ok(mcp.call("create_object", doc_name=doc, obj_type="Part::Box", obj_name="Box"))
    result = mcp.call("create_object", doc_name=doc, obj_type="Draft::Rectangle", obj_name="DraftRect",
                      obj_properties={"Length": 20, "Height": 10})
    assert result.is_error, result.text
    payload = _payload(result)
    assert payload["error_code"] == "UNSUPPORTED_DRAFT_TYPE", result.text
    assert "Draft.make_rectangle" in payload["error"]
    assert payload["committed"] is False
    assert_ok(mcp.call("close_document", doc_name=doc))
    assert_clean(gui_log)
