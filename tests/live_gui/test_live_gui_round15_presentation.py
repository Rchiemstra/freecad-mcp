"""Round 15 presentation admission after TechDraw and STEP import."""
import pytest
from tests.live_gui._support import assert_clean, assert_ok

pytestmark = pytest.mark.live_gui


def _fixture(mcp, doc, drawing):
    assert_ok(mcp.call('create_document', name=doc))
    code = "import FreeCAD\ndoc=FreeCAD.getDocument(%r)\nbox=doc.addObject('Part::Box','Box')\nbox.Length=40;box.Width=20;box.Height=10\n" % doc
    if drawing:
        code += """page=doc.addObject('TechDraw::DrawPage','Page')
tpl=doc.addObject('TechDraw::DrawSVGTemplate','Template')
tpl.Template='/workspace/build/debug/share/Mod/TechDraw/Templates/Default_Template_A4_Landscape.svg'
page.Template=tpl
view=doc.addObject('TechDraw::DrawViewPart','View');view.Source=[box];page.addView(view)
pg=doc.addObject('TechDraw::DrawProjGroup','ProjGroup');pg.Source=[box];page.addView(pg)
doc.recompute()
"""
    assert_ok(mcp.call('execute_code', document=doc, recompute='target', execution_mode='gui', code=code))
    path = '/tmp/' + doc + '.step'
    assert_ok(mcp.call('export_step', doc_name=doc, file_path=path, obj_names=['Box']))
    assert_ok(mcp.call('open_document', path=path))
    assert_ok(mcp.call('list_documents'))
    report = assert_ok(mcp.call('get_report_view', max_lines=200))
    assert 'mutation is unavailable from a non-owner thread during an atomic presentation callback' not in report.text, report.text


def test_step_import_without_drawing(mcp, gui_log):
    assert_ok(mcp.call('get_report_view', clear=True))
    _fixture(mcp, 'R15PlainStep', False)
    assert_clean(gui_log)


def test_techdraw_step_import_has_no_admission_errors(mcp, gui_log):
    assert_ok(mcp.call('get_report_view', clear=True))
    _fixture(mcp, 'R15DrawingStep', True)
    assert_clean(gui_log)

