"""Round 22: body recompute deferral must reach caller-visible feedback."""

import pytest

from tests.live_gui._support import assert_clean, assert_ok

pytestmark = pytest.mark.live_gui


@pytest.mark.parametrize("call_recompute", [False, True], ids=["happy_print", "defect_deferred"])
def test_round22_execute_target_recompute_feedback(mcp, gui_log, call_recompute):
    doc = "R22Feat"
    assert_ok(mcp.call("create_document", name=doc))
    try:
        code = "print('inspection')"
        if call_recompute:
            code = f"doc = FreeCAD.getDocument('{doc}')\nr = doc.recompute()\nprint('recompute-return', r)"
        result = assert_ok(mcp.call("execute_code", code=code, document=doc,
                                    recompute="target", execution_mode="gui"))
        if call_recompute:
            assert "recompute-return 0" in result.text
            assert "deferred" in result.text.lower(), result.text
            assert "target recompute" in result.text.lower(), result.text
        else:
            assert "inspection" in result.text
            assert "deferred" not in result.text.lower()
    finally:
        assert_ok(mcp.call("close_document", doc_name=doc))
    assert_clean(gui_log)
