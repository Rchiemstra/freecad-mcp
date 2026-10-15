"""Round 14 Draft API imports on the document owner thread."""
from __future__ import annotations

import pytest

from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round5 import _payload

pytestmark = pytest.mark.live_gui


def test_draft_hatch_import_freecad_tests(mcp, gui_log, freecad_source_root):
    # No target document: these compatibility controls must run on Qt's main
    # thread, and explicitly exercise owner-thread imports themselves.
    source = freecad_source_root / "src/Mod/Draft/drafttests/test_import_gui.py"
    code = f"""import importlib.util, unittest, io
spec=importlib.util.spec_from_file_location('r14_import_gui', {str(source)!r})
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


_DRAFT_FACTORY_CONTROLS = (
    "test_annotation_presentation_after_commit_without_recompute",
    "test_default_copies_on_document_owner_thread",
    "test_factories_on_document_owner_thread",
    "test_factories_on_main_thread",
)


@pytest.mark.parametrize("control,factory_half", [
    pytest.param(control, half, id=control + (f"_half_{half + 1}" if half is not None else ""))
    for control in _DRAFT_FACTORY_CONTROLS
    for half in ((0, 1) if control == "test_factories_on_document_owner_thread" else (None,))
])
def test_draft_all_factory_thread_controls(mcp, gui_log, freecad_source_root, control, factory_half):
    # The combined suite opens over 100 fixture documents and exceeds the
    # 120s GUI request deadline on a constrained software-rendering CI worker.
    # The owner factory method alone took 112s with one CPU; divide its cases
    # into disjoint halves too, retaining the same deadline for every call.
    source = freecad_source_root / "src/Mod/Draft/drafttests/test_owner_thread_gui.py"
    code = f"""import importlib.util, unittest, io
spec=importlib.util.spec_from_file_location('draft_owner_controls', {str(source)!r})
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
controls=unittest.defaultTestLoader.getTestCaseNames(module.DraftOwnerThreadFactories)
assert set(controls) == set({_DRAFT_FACTORY_CONTROLS!r}), 'Update live Draft control list: ' + repr(controls)
output=io.StringIO()
case=module.DraftOwnerThreadFactories({control!r})
factory_half={factory_half!r}
if factory_half is not None:
    all_cases=case._cases
    def half_cases(*args, **kwargs):
        cases=all_cases(*args, **kwargs)
        middle=(len(cases) + 1) // 2
        return cases[:middle] if factory_half == 0 else cases[middle:]
    case._cases=half_cases
suite=unittest.TestSuite([case])
result=unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
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
