"""Live checks for the defects the ninth agent stress run reported."""

from __future__ import annotations

import pytest

from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round5 import _payload, _rejected
from tests.live_gui.test_live_gui_stress import _part_body

pytestmark = pytest.mark.live_gui


def _names(mcp, doc_name: str) -> set[str]:
    listed = _payload(assert_ok(mcp.call("get_objects", doc_name=doc_name)))
    return {item["Name"] for item in listed["objects"]}


def test_a_pattern_over_the_cap_is_refused_and_a_small_one_commits(mcp, gui_log):
    """500 occurrences wedged the GUI thread inside an OCC boolean cut."""

    _part_body(mcp, "LivePat", length=10)
    _rejected(
        mcp.call(
            "linear_pattern_feature",
            doc_name="LivePat",
            feature_name="Pad",
            pattern_name="Huge",
            length=20,
            occurrences=500,
            body_name="Body",
        ),
        "split the pattern or use fewer occurrences",
    )
    assert "Huge" not in _names(mcp, "LivePat")
    assert_ok(
        mcp.call(
            "linear_pattern_feature",
            doc_name="LivePat",
            feature_name="Pad",
            pattern_name="Row",
            length=20,
            occurrences=4,
            body_name="Body",
        )
    )
    assert "Row" in _names(mcp, "LivePat")
    assert_ok(mcp.call("close_document", doc_name="LivePat"))
    assert_clean(gui_log)
