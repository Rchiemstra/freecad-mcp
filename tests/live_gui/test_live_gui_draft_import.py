"""Round 14 Draft API imports on the document owner thread."""
from __future__ import annotations

import pytest

from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round5 import _payload

pytestmark = pytest.mark.live_gui


def test_draft_hatch_import_freecad_tests(mcp, gui_log):
    # No target document: these compatibility controls must run on Qt's main
    # thread, and explicitly exercise owner-thread imports themselves.
    code = """import importlib.util, unittest, io
spec=importlib.util.spec_from_file_location('r14_import_gui', '/workspace/src/Mod/Draft/drafttests/test_import_gui.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
output=io.StringIO()
result=unittest.TextTestRunner(stream=output, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(module.DraftHatchImportIsolation))
assert result.wasSuccessful(), output.getvalue()
print(output.getvalue())
"""
    assert_ok(mcp.call("execute_code", execution_mode="gui", recompute="none", code=code))
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
    # Separate intermittent renderer finding seen during the combined round-14
    # checks; keep import/API failures fatal and permit only its exact line.
    assert_clean(gui_log, r"Coin warning in \[faceset\]::GLRender\(\): Erroneous polygon detected\. Ignoring \(offset: 4, \[-1 2 3\]\)\. Should be within  \[0, 7\] This message will only be shown once, but more errors might be present")


def test_draft_all_factory_thread_controls(mcp, gui_log):
    code = """import importlib.util, unittest, io
spec=importlib.util.spec_from_file_location('draft_owner_controls', '/workspace/src/Mod/Draft/drafttests/test_owner_thread_gui.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
output=io.StringIO()
result=unittest.TextTestRunner(stream=output, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(module.DraftOwnerThreadFactories))
assert result.wasSuccessful(), output.getvalue()
print(output.getvalue())
"""
    result = mcp.call("execute_code", execution_mode="gui", recompute="none", code=code)
    assert result.ok, result.text
    # The unmodified main-thread controls also emit this exact Coin diagnostic
    # when their fixture documents close. Owner-thread API errors remain fatal.
    assert_clean(gui_log, r"Coin error in SoGroup::removeChild\(\): tried to remove non-existent child 0x[0-9a-f]+ \((?:Switch|Separator)\)$")


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


def test_owner_draft_text_presentation(mcp, gui_log):
    # With no document resolved this harness runs on Qt's main thread. Submit
    # the factory to a document owner, then inspect Coin after GUI catch-up.
    code = """import threading, Draft, FreeCAD as App
from Test.GuiRecompute import _pump_gui_until, recompute_document, close_document
from draftutils import gui_utils
doc=App.newDocument('DraftOwnerVisibleText')
errors=[]
def create_text():
    assert not gui_utils.on_gui_thread()
    Draft.make_text('Owner visible', height=17, screen=False)
def worker():
    try:
        result=doc.commitCompatibilityMutation(create_text, structural=True, recompute=False)
        assert result['committed'], result
    except BaseException as exc:
        errors.append(exc)
try:
    thread=threading.Thread(target=worker)
    thread.start()
    _pump_gui_until(lambda: not thread.is_alive(), 60)
    thread.join()
    assert not errors, errors
    recompute_document(doc)
    text=doc.getObject('Text')
    assert gui_utils.on_gui_thread()
    assert type(text.ViewObject.Proxy).__name__ == 'ViewProviderText'
    assert text.ViewObject.Visibility
    assert text.ViewObject.isVisible()
    assert text.ViewObject.DisplayMode == 'World'
    assert text.ViewObject.FontSize.Value == 17
    assert text.ViewObject.Proxy.text_wld.string.getValues() == ['Owner visible']
    assert text.ViewObject.Proxy.font.size.getValue() == 17 * text.ViewObject.ScaleMultiplier
    print('owner text visible, height=17')
finally:
    close_document(doc)
"""
    result = mcp.call("execute_code", execution_mode="gui", recompute="none", code=code)
    assert result.ok, result.text
    assert "owner text visible, height=17" in result.text
    assert_clean(gui_log)
