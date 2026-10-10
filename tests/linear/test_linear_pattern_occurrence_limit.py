"""linear_pattern_feature must refuse occurrence counts that wedge the GUI.

A 500-occurrence pattern of a pocket runs PartDesign::Transformed::execute on
the document owner thread. That is genuine OCC work (one boolean cut per
copy), not a Python loop, and it kept the GUI unresponsive for more than
30 minutes.
"""

from __future__ import annotations

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.feature_mutate_support import (
    MAX_PATTERN_OCCURRENCES,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.linear_pattern_feature import (
    build_linear_pattern_feature_request,
    run_linear_pattern_feature,
)
from tests.typed_feature_fakes import FeatureDocument, collaborators, prepare_document

pytestmark = pytest.mark.unit


def _run(occurrences: int, pattern_name: str = "Array"):
    events: list[str] = []
    document = FeatureDocument(events)
    prepare_document("pattern", document)
    collab, _api = collaborators(document, events)
    result = run_linear_pattern_feature(
        collab,
        "Doc",
        "Pad",
        pattern_name,
        40.0,
        occurrences,
        "X_Axis",
        "Body",
        False,
    )
    return result, events, document


@pytest.mark.parametrize("occurrences", [2, 4, MAX_PATTERN_OCCURRENCES])
def test_occurrences_up_to_the_cap_commit(occurrences):
    result, events, document = _run(occurrences)

    assert not isinstance(result, dict) or result["success"] is True
    assert result["success"] is True
    assert result["feature"] == "Array"
    assert "commit" in events
    assert "Array" in document.objects


@pytest.mark.parametrize("occurrences", [MAX_PATTERN_OCCURRENCES + 1, 500])
def test_occurrences_above_the_cap_are_rejected_before_create(occurrences):
    result, events, document = _run(occurrences, pattern_name="LinHuge")

    assert isinstance(result, dict)
    assert result["success"] is False
    assert result["outcome"] == "rejected"
    assert result["committed"] is False
    assert result["error_code"] == "INVALID_ARGUMENT"
    assert "must be <= 100" in result["error"]
    assert "split the pattern or use fewer occurrences" in result["error"]
    assert events == []
    assert "LinHuge" not in document.objects


def test_build_rejects_the_cap_before_a_request_exists():
    failure = build_linear_pattern_feature_request(
        "Doc", "Pad", "LinHuge", 20.0, 500
    )

    assert isinstance(failure, dict)
    assert failure["error_code"] == "INVALID_ARGUMENT"
    accepted = build_linear_pattern_feature_request(
        "Doc", "Pad", "Row", 20.0, 4
    )
    assert not isinstance(accepted, dict)
