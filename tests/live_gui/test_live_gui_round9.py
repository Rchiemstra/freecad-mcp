"""Live checks for the defects the ninth agent stress run reported."""

from __future__ import annotations

import re

import pytest

from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round5 import _payload, _rejected
from tests.live_gui.test_live_gui_stress import _part_body

pytestmark = pytest.mark.live_gui


def _names(mcp, doc_name: str) -> set[str]:
    listed = _payload(assert_ok(mcp.call("get_objects", doc_name=doc_name)))
    return {item["Name"] for item in listed["objects"]}


def _tip(mcp, doc_name: str) -> str:
    result = assert_ok(mcp.call(
        "execute_code",
        document=doc_name,
        execution_mode="worker",
        read_only=True,
        code=(
            "import FreeCAD as App\n"
            f"body = App.getDocument({doc_name!r}).getObject('Body')\n"
            "print(body.Tip.Name if body is not None and body.Tip else '')\n"
        ),
    ))
    output = ""
    if result.payload:
        output = str(result.payload.get("output") or "")
    if not output.strip():
        output = result.text
    names = re.findall(r"(?m)^([A-Za-z_][A-Za-z0-9_]*)$", output)
    assert names, result.text[:600]
    return names[-1]


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


def test_polar_pattern_of_a_pattern_is_refused_and_the_tip_stays(mcp, gui_log):
    """A LinearPattern is not a FeatureAddSub, so it cannot be patterned."""

    _part_body(mcp, "LiveSrc", length=10)
    assert_ok(
        mcp.call(
            "linear_pattern_feature",
            doc_name="LiveSrc",
            feature_name="Pad",
            pattern_name="Row",
            length=20,
            occurrences=4,
            body_name="Body",
        )
    )
    assert _tip(mcp, "LiveSrc") == "Row"
    _rejected(
        mcp.call(
            "polar_pattern_feature",
            doc_name="LiveSrc",
            feature_name="Row",
            pattern_name="HolePolar",
            occurrences=4,
            angle=360,
            axis="Z_Axis",
            body_name="Body",
        ),
        "Only additive and subtractive features can be transformed",
    )
    assert "HolePolar" not in _names(mcp, "LiveSrc")
    assert _tip(mcp, "LiveSrc") == "Row"
    assert_ok(mcp.call("close_document", doc_name="LiveSrc"))
    assert_clean(gui_log)


def test_find_faces_positive_z_returns_only_the_top_face(mcp, gui_log):
    """+Z used to return the bottom face first because parallel included -Z."""

    _part_body(mcp, "LiveFace", length=10)
    found = _payload(assert_ok(mcp.call(
        "find_faces",
        doc_name="LiveFace",
        object_name="Pad",
        type="Plane",
        normal_approx={"x": 0, "y": 0, "z": 1},
    )))
    results = found["results"]
    assert found["count"] == 1
    assert len(results) == 1
    face = results[0]
    assert face["global_normal"]["z"] > 0
    assert face["global_center"]["z"] == pytest.approx(10.0)
    assert_ok(mcp.call("close_document", doc_name="LiveFace"))
    assert_clean(gui_log)
