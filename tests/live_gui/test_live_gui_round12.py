"""Regression coverage for live GUI stress round 12 and import addon feedback."""
from __future__ import annotations

import pytest
from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round5 import _payload

pytestmark = pytest.mark.live_gui


def test_property_projection_omits_missing_properties_and_aliases(mcp, gui_log):
    assert_ok(mcp.call("create_document", name="R12Properties"))
    assert_ok(mcp.call("body_create", doc_name="R12Properties", body_name="Body"))
    assert_ok(mcp.call("spreadsheet_create", doc_name="R12Properties", sheet_name="Sheet"))
    assert_ok(mcp.call("spreadsheet_set_cells", doc_name="R12Properties", sheet_name="Sheet",
                       cells=[{"address": "A1", "alias": "Width", "value": "40 mm"}]))
    rows = _payload(assert_ok(mcp.call("get_objects", doc_name="R12Properties",
                                      include_properties=["Type", "Width", "Length"])))
    for row in rows["objects"]:
        if row["Name"] in {"Body", "Sheet"}:
            assert row["Properties"] == {}
    assert_ok(mcp.call("close_document", doc_name="R12Properties"))
    assert_clean(gui_log)



def test_part_and_body_origins_have_owners(mcp, gui_log):
    assert_ok(mcp.call("create_document", name="R12Tree"))
    assert_ok(mcp.call("create_part_container", doc_name="R12Tree", part_name="Part"))
    assert_ok(mcp.call("body_create", doc_name="R12Tree", body_name="Body"))
    tree = _payload(assert_ok(mcp.call("get_document_tree", doc_name="R12Tree", max_depth=3)))
    assert {row["Name"] for row in tree["roots"]} == {"Part", "Body"}
    for row in tree["roots"]:
        origin = next(child for child in row["children"] if child["TypeId"] == "App::Origin")
        assert len(origin["children"]) >= 6
    assert_ok(mcp.call("close_document", doc_name="R12Tree"))
    assert_clean(gui_log)

