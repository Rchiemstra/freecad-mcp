"""Unconfigured TechDraw templates must not flood the live Report view."""
from __future__ import annotations

import pytest

from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round5 import _payload

pytestmark = pytest.mark.live_gui


@pytest.mark.parametrize("configured", [True, False], ids=["configured", "empty"])
def test_techdraw_template_redraws_quietly(mcp, gui_log, configured, freecad_source_root):
    doc = "R14TDConfigured" if configured else "R14TDEmpty"
    assert_ok(mcp.call("create_document", name=doc))
    assert_ok(mcp.call("create_object", doc_name=doc, obj_type="Part::Box", obj_name="Box"))
    template = freecad_source_root / "src/Mod/TechDraw/TDTest/TestTemplate.svg"
    setup = f"tpl.Template={str(template)!r}\n" if configured else ""
    assert_ok(mcp.call("execute_code", document=doc, execution_mode="gui", recompute="target",
                       code=f"doc=FreeCAD.getDocument('{doc}')\npage=doc.addObject('TechDraw::DrawPage','TDPage')\ntpl=doc.addObject('TechDraw::DrawSVGTemplate','TDTemplate')\n{setup}page.Template=tpl\nprint(page.Name)"))
    # Capture the Report after unrelated mutations too: repeated redraws used
    # to reparse the absent SVG and add another identical error every time.
    for _ in range(3):
        assert_ok(mcp.call("translate", doc_name=doc, obj_name="Box", dx=1, dy=0, dz=0))
        report = assert_ok(mcp.call("get_report_view", max_lines=100))
        assert "QGISVGTemplate::createClickHandles - xml loading error" not in report.text, report.text
        assert_clean(gui_log)
    assert_ok(mcp.call("close_document", doc_name=doc))
    assert_clean(gui_log)


def test_techdraw_core_gui_regressions(mcp, gui_log, freecad_source_root):
    # With no active document execute_code uses the GUI thread. The FreeCAD
    # test owns its documents and uses the standard asynchronous GUI helpers.
    # Other stress cases intentionally retain their modeling document.
    # Establish the lifecycle test's unscoped execution precondition explicitly.
    for name in _payload(assert_ok(mcp.call("list_documents")))["value"]:
        assert_ok(mcp.call("close_document", doc_name=name))
    source = freecad_source_root / "src/Mod/TechDraw/TestTechDrawGui.py"
    code = f"""import importlib.util, unittest, io
spec=importlib.util.spec_from_file_location('r14_td_gui', {str(source)!r})
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
output=io.StringIO()
result=unittest.TextTestRunner(stream=output, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(module.SVGTemplateRedrawTest))
assert result.wasSuccessful(), output.getvalue()
print(output.getvalue())
"""
    result = mcp.call("execute_code", execution_mode="gui", recompute="none", code=code)
    assert result.ok, result.text
    assert_clean(gui_log)
