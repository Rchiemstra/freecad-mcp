"""Joint creation must validate an explicitly requested solve before commit."""

import pytest

from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round15_assembly import _assembly
from tests.live_gui.test_live_gui_round5 import _payload

pytestmark = pytest.mark.live_gui


def test_create_joint_with_solve_commits_valid_joint(mcp, gui_log):
    doc = "JointSolveGood"
    try:
        _assembly(mcp, doc)
        result = _payload(assert_ok(mcp.call("solve_assembly", doc_name=doc, assembly_name="Asm")))
        assert result["solver_status"] == "0"
    finally:
        assert_ok(mcp.call("close_document", doc_name=doc))
    assert_clean(gui_log)


def test_create_joint_with_solve_rolls_back_conflict(mcp, gui_log):
    doc = "JointSolveConflict"
    try:
        _assembly(mcp, doc)
        before = _payload(assert_ok(mcp.call("get_objects", doc_name=doc, fields=["Name", "Placement"])))
        result = mcp.call("create_assembly_joint", doc_name=doc, assembly_name="Asm",
                          joint_type="Distance", ref1_component="A", ref2_component="B",
                          ref1_element="Face1", ref2_element="Face1", label="BadDist",
                          properties={"Distance": 100}, solve=True)
        assert result.is_error, result.text
        payload = _payload(result)
        assert payload["error_code"] == "ASSEMBLY_SOLVE_FAILED", result.text
        assert "conflicting constraints" in payload["error"]
        assert "status -3" in payload["error"]
        assert "BadDist" in payload["error"]
        assert payload["committed"] is False
        assert payload["rollback_succeeded"] is True
        after = _payload(assert_ok(mcp.call("get_objects", doc_name=doc, fields=["Name", "Placement"])))
        assert after == before
        solved = _payload(assert_ok(mcp.call("solve_assembly", doc_name=doc, assembly_name="Asm")))
        assert solved["solver_status"] == "0"
    finally:
        assert_ok(mcp.call("close_document", doc_name=doc))
    assert_clean(gui_log, r"Assembly solve: joint '(?:BadDist|Fixed)' does not hold")
