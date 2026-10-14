"""Snapshot recovery regressions from round 16."""

import pytest

from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round5 import _payload

pytestmark = pytest.mark.live_gui


def _snapshot_pad(mcp, doc):
    assert_ok(mcp.call("create_document", name=doc))
    assert_ok(mcp.call("body_create", doc_name=doc, body_name="Body"))
    assert_ok(mcp.call("sketch_create", doc_name=doc, sketch_name="Sketch",
                       body_name="Body", attach_to="XY_Plane"))
    assert_ok(mcp.call("sketch_add_rectangle", doc_name=doc, sketch_name="Sketch",
                       x1=0, y1=0, x2=20, y2=15))
    assert_ok(mcp.call("pad_feature", doc_name=doc, sketch_name="Sketch",
                       pad_name="Pad", length=8, body_name="Body", strict=True))
    return _payload(assert_ok(mcp.call("snapshot", doc_name=doc)))["snapshot_id"]


@pytest.mark.parametrize("broken", [False, True], ids=["healthy_edit", "broken_hole"])
def test_restore_replaces_post_snapshot_state(mcp, gui_log, broken):
    doc = "R16RestoreBroken" if broken else "R16RestoreHealthy"
    snapshot_id = _snapshot_pad(mcp, doc)
    code = "import FreeCAD as App\ndoc=App.getDocument(%r)\n" % doc
    if broken:
        code += "body=doc.getObject('Body')\nh=doc.addObject('PartDesign::Hole','Hole1')\nbody.addObject(h)\n"
    else:
        code += "doc.getObject('Pad').Length=12\ndoc.addObject('Part::Box','Extra')\n"
    assert_ok(mcp.call("execute_code", document=doc, recompute="none",
                       execution_mode="gui", code=code))
    result = mcp.call("restore", doc_name=doc, snapshot_id=snapshot_id)
    objects = _payload(assert_ok(mcp.call("get_objects", doc_name=doc,
                                         fields=["Name"], page_size=30)))
    assert_ok(result)
    assert "Hole1" not in str(objects)
    assert "Extra" not in str(objects)
    volume = _payload(assert_ok(mcp.call("measure_volume", doc_name=doc, obj_name="Pad")))
    assert volume["volume_mm3"] == pytest.approx(2400)
    assert_ok(mcp.call("close_document", doc_name=doc))
    assert_clean(gui_log)
