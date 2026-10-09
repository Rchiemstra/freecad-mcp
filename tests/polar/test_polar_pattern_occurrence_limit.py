"""polar_pattern_feature shares the linear pattern occurrence cap."""

from __future__ import annotations

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.feature_mutate_support import (
    MAX_PATTERN_OCCURRENCES,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.polar_pattern_feature import (
    build_polar_pattern_feature_request,
    run_polar_pattern_feature,
)
from tests.typed_feature_fakes import FeatureDocument, collaborators, prepare_document

pytestmark = pytest.mark.unit


def _run(occurrences: int, pattern_name: str = "BoltCircle"):
    events: list[str] = []
    document = FeatureDocument(events)
    prepare_document("pattern", document)
    collab, _api = collaborators(document, events)
    result = run_polar_pattern_feature(
        collab,
        "Doc",
        "Pad",
        pattern_name,
        occurrences,
        360.0,
        "Z_Axis",
        "Body",
        False,
    )
    return result, events, document


@pytest.mark.parametrize("occurrences", [4, MAX_PATTERN_OCCURRENCES])
def test_occurrences_up_to_the_cap_commit(occurrences):
    result, events, document = _run(occurrences)

    assert result["success"] is True
    assert "commit" in events
    assert "BoltCircle" in document.objects


@pytest.mark.parametrize("occurrences", [MAX_PATTERN_OCCURRENCES + 1, 500])
def test_occurrences_above_the_cap_are_rejected_before_create(occurrences):
    result, events, document = _run(occurrences, pattern_name="PolHuge")

    assert result["success"] is False
    assert result["error_code"] == "INVALID_ARGUMENT"
    assert result["committed"] is False
    assert "split the pattern or use fewer occurrences" in result["error"]
    assert events == []
    assert "PolHuge" not in document.objects


def test_build_accepts_four_and_rejects_five_hundred():
    assert not isinstance(
        build_polar_pattern_feature_request("Doc", "Pad", "Ok", 4),
        dict,
    )
    failure = build_polar_pattern_feature_request("Doc", "Pad", "PolHuge", 500)
    assert isinstance(failure, dict)
    assert "must be <= 100" in failure["error"]
