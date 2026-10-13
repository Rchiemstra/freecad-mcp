"""Body ownership regressions from round 14."""
from __future__ import annotations

import pytest

from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round5 import _payload
from tests.live_gui.test_live_gui_orphan_pad import _healthy_pad

pytestmark = pytest.mark.live_gui


def test_owned_fillet_commits(mcp, gui_log):
    doc = "R14OwnedFillet"
    assert_ok(mcp.call("create_document", name=doc))
    assert_ok(mcp.call("body_create", doc_name=doc, body_name="Body"))
    _healthy_pad(mcp, doc)
    result = assert_ok(mcp.call("fillet_feature", doc_name=doc, base_feature="OwnedPad",
                               fillet_name="Fillet", radius=1, body_name="Body"))
    assert _payload(result)["committed"] is True
    volume = _payload(assert_ok(mcp.call("measure_volume", doc_name=doc, obj_name="Fillet")))
    assert 0 < volume["volume_mm3"] < 720
    assert_ok(mcp.call("close_document", doc_name=doc))
    assert_clean(gui_log)


@pytest.mark.parametrize("other_body", [False, True], ids=["external_box", "other_body"])
def test_external_fillet_rejected_without_moving_tip(mcp, gui_log, other_body):
    doc = "R14FilletOther" if other_body else "R14FilletExternal"
    assert_ok(mcp.call("create_document", name=doc))
    assert_ok(mcp.call("body_create", doc_name=doc, body_name="Body"))
    _healthy_pad(mcp, doc)
    base = "PlainBox"
    if other_body:
        assert_ok(mcp.call("body_create", doc_name=doc, body_name="Other"))
        assert_ok(mcp.call("execute_code", document=doc, execution_mode="gui", recompute="target",
                           code=f"doc=FreeCAD.getDocument('{doc}')\nbase=doc.getObject('Other').newObject('PartDesign::Feature','External')\nimport Part\nbase.Shape=Part.makeBox(20,10,5)"))
        base = "External"
    else:
        assert_ok(mcp.call("create_object", doc_name=doc, obj_type="Part::Box", obj_name=base,
                           obj_properties={"Length": 20, "Width": 10, "Height": 5}))
    before = _payload(assert_ok(mcp.call("get_object", doc_name=doc, obj_name="Body")))
    result = mcp.call("fillet_feature", doc_name=doc, base_feature=base,
                      fillet_name="FilletBad", radius=1, body_name="Body")
    after = _payload(assert_ok(mcp.call("get_object", doc_name=doc, obj_name="Body")))
    assert result.is_error, result.text
    payload = _payload(result)
    for key, expected in {"success": False, "error_code": "BASE_NOT_IN_BODY",
                          "committed": False, "rollback_succeeded": True,
                          "native_status": "ApplyFailed"}.items():
        assert payload[key] == expected, result.text
    for key in ("Tip", "Group", "Placement", "BaseFeature"):
        assert after["object_data"]["Properties"][key] == before["object_data"]["Properties"][key]
    state = assert_ok(mcp.call("execute_code", document=doc, execution_mode="worker", read_only=True,
                              code=f"doc=FreeCAD.getDocument('{doc}')\nassert doc.getObject('Body').Tip.Name == 'OwnedPad'\nassert doc.getObject('FilletBad') is None"))
    assert state.ok
    volume = _payload(assert_ok(mcp.call("measure_volume", doc_name=doc, obj_name="OwnedPad")))
    assert volume["volume_mm3"] == pytest.approx(720)
    assert_ok(mcp.call("close_document", doc_name=doc))
    assert_clean(gui_log)
