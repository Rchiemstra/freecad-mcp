"""Empty Boolean results are rejected and rolled back."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.boolean_difference import (
    run_boolean_difference,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.boolean_intersection import (
    run_boolean_intersection,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.boolean_union import (
    run_boolean_union,
)
from tests.typed_feature_fakes import FeatureDocument, collaborators, prepare_document

pytestmark = pytest.mark.unit

_CASES = [
    ("intersection", run_boolean_intersection),
    ("difference", run_boolean_difference),
    ("union", run_boolean_union),
]


class _EmptyAfterRecompute(FeatureDocument):
    def recompute(self) -> None:
        super().recompute()
        created = self.objects["Result"]
        created.Shape = SimpleNamespace(isNull=lambda: False, Faces=[], Volume=0.0)


@pytest.mark.parametrize(("kind", "run"), _CASES)
def test_a_solid_boolean_commits(kind, run):
    events: list[str] = []
    document = FeatureDocument(events)
    prepare_document("boolean", document)
    collab, _api = collaborators(document, events)

    result = run(collab, "Doc", "Shape1", "Shape2", "Result")

    assert kind in {"intersection", "difference", "union"}
    assert result["success"] is True
    assert result["outcome"] == "committed"
    assert "Result" in document.objects


@pytest.mark.parametrize(("kind", "run"), _CASES)
def test_an_empty_boolean_is_rejected_and_rolled_back(kind, run):
    events: list[str] = []
    document = _EmptyAfterRecompute(events)
    prepare_document("boolean", document)
    collab, _api = collaborators(document, events)

    result = run(collab, "Doc", "Shape1", "Shape2", "Result")

    assert kind in {"intersection", "difference", "union"}
    assert result["success"] is False
    assert result["error_code"] == "EMPTY_BOOLEAN_RESULT"
    assert "empty" in result["error"]
    assert result["committed"] is False
    assert "Result" not in document.objects
    assert "commit" not in events
