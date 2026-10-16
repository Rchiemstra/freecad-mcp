"""Factory presentation must wait for the target document lane."""

import pytest

from tests.live_gui._support import assert_clean

pytestmark = pytest.mark.live_gui


def test_owner_view_property_callback_delivery(mcp, gui_log, freecad_source_root):
    source = freecad_source_root / "src/Mod/Test/GuiDocument.py"
    code = f"""import importlib.util, unittest, io
spec=importlib.util.spec_from_file_location('presentation_admission_regression', {str(source)!r})
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
output=io.StringIO()
case=module.TestGuiDocument('testPresentationCallbackWaitsForDocumentLane')
result=unittest.TextTestRunner(stream=output, verbosity=2).run(unittest.TestSuite([case]))
assert result.wasSuccessful(), output.getvalue()
print(output.getvalue())
"""
    result = mcp.call("execute_code", execution_mode="gui", recompute="none", code=code)
    assert result.ok, result.text
    assert_clean(gui_log)
