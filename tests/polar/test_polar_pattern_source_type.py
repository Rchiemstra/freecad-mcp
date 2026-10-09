"""polar_pattern_feature only transforms additive or subtractive features.

Patterning an existing LinearPattern used to create the PolarPattern and
fail only at recompute. The source is checked before create, so the body
tip stays where it was.
"""

from __future__ import annotations

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.polar_pattern_feature import (
    run_polar_pattern_feature,
)
from tests.typed_feature_fakes import FeatureDocument, FeatureObj, collaborators, prepare_document

pytestmark = pytest.mark.unit


def _document():
    events: list[str] = []
    document = FeatureDocument(events)
    prepare_document("pattern", document)
    return events, document, collaborators(document, events)[0]


def _run(collab, feature_name: str, pattern_name: str):
    return run_polar_pattern_feature(
        collab,
        "Doc",
        feature_name,
        pattern_name,
        4,
        360.0,
        "Z_Axis",
        "Body",
        False,
    )


def test_pad_source_commits_and_becomes_the_tip():
    events, document, collab = _document()

    result = _run(collab, "Pad", "BoltCircle")

    assert result["success"] is True
    assert result["committed"] is True
    assert "BoltCircle" in document.objects
    assert document.objects["Body"].Tip is document.objects["BoltCircle"]
    assert "commit" in events


def test_pattern_source_is_rejected_before_create_and_the_tip_stays():
    events, document, collab = _document()
    body = document.objects["Body"]
    source = FeatureObj("Row", "PartDesign::LinearPattern", document)
    document.objects["Row"] = source
    body.Group.append(source)
    body.Tip = source

    result = _run(collab, "Row", "HolePolar")

    assert result["success"] is False
    assert result["outcome"] == "rejected"
    assert result["committed"] is False
    assert result["error_code"] == "INVALID_ARGUMENT"
    assert "Only additive and subtractive features can be transformed" in result["error"]
    assert "HolePolar" not in document.objects
    assert body.Tip is source
    assert events == ["abort"]
    assert document.add_calls == 0
