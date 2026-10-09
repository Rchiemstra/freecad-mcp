"""Live checks for the defects the eighth agent stress run reported."""

from __future__ import annotations

import pytest

from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round5 import _payload

pytestmark = pytest.mark.live_gui


def _label(mcp, doc_name: str, obj_name: str) -> str:
    listed = _payload(assert_ok(mcp.call("get_objects", doc_name=doc_name)))
    row = next(item for item in listed["objects"] if item["Name"] == obj_name)
    return row["Label"]


def test_a_live_property_edit_commits(mcp, gui_log):
    """A live execute_code body that only changes an App property commits."""

    assert_ok(mcp.call("create_document", name="LiveExecOk"))
    assert_ok(mcp.call("create_object", doc_name="LiveExecOk", obj_type="Part::Box",
                       obj_name="Box"))

    assert_ok(mcp.call(
        "execute_code",
        document="LiveExecOk",
        execution_mode="gui",
        read_only=False,
        code="import FreeCAD as App\n"
             "App.getDocument('LiveExecOk').getObject('Box').Label = 'Committed'\n",
    ))

    assert _label(mcp, "LiveExecOk", "Box") == "Committed"
    assert_ok(mcp.call("close_document", doc_name="LiveExecOk"))
    assert_clean(gui_log)


def test_freecadgui_inside_a_live_body_is_rolled_back(mcp, gui_log):
    """FreeCADGui.getDocument runs off the Qt main thread inside the commit.
    The tool fails, nothing commits, and the earlier Label edit is undone."""

    assert_ok(mcp.call("create_document", name="LiveExecGui"))
    assert_ok(mcp.call("create_object", doc_name="LiveExecGui", obj_type="Part::Box",
                       obj_name="Box"))

    failed = mcp.call(
        "execute_code",
        document="LiveExecGui",
        execution_mode="gui",
        read_only=False,
        code="import FreeCAD as App\n"
             "import FreeCADGui\n"
             "App.getDocument('LiveExecGui').getObject('Box').Label = 'RolledBack'\n"
             "FreeCADGui.getDocument('LiveExecGui')\n",
    )

    assert not failed.ok, failed.text[:600]
    assert failed.payload["success"] is False
    assert failed.payload["committed"] is False
    assert "may only be used from the main thread" in failed.payload["error"]
    assert _label(mcp, "LiveExecGui", "Box") == "Box"
    assert_ok(mcp.call("close_document", doc_name="LiveExecGui"))
    # FreeCAD logs the main-thread refusal; the tool result carries the same text.
    assert_clean(gui_log, r"may only be used from the main thread")
