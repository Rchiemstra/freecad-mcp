"""Unit coverage for the typed ``common_volume_along_path`` query slice."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import common_volume_along_path as subject
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import measure_path_actions
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.common_volume_along_path import run_common_volume_along_path
from tests.typed_rpc_fakes import FakeDocument, FakeObject, collaborators

pytestmark = pytest.mark.unit


def _payload() -> dict[str, object]:
    return {
        "moving_object": "Mover",
        "sample_count": 1,
        "volume_threshold_mm3": 1e-6,
        "max_common_volume_mm3": 0.0,
        "any_collision": False,
        "samples": [],
    }


def test_common_volume_along_path_observed_without_native_mutation():
    events: list[str] = []
    document = FakeDocument(events)
    document.objects["Mover"] = FakeObject("Mover", "Part::Box")
    document.objects["Wall"] = FakeObject("Wall", "Part::Box")
    collab, _api = collaborators(document, events)
    with patch.object(measure_path_actions, "common_volume_along_path", return_value=_payload()):
        result = run_common_volume_along_path(
            collab,
            "Doc",
            "Mover",
            ["Wall"],
            None,
            2,
            [{"x": 0, "y": 0, "z": 0}],
        )

    assert result["success"] is True
    assert result["outcome"] == "observed"
    assert result["moving_object"] == "Mover"
    assert "commit" not in events


def test_invalid_names_abort_without_recompute_or_commit():
    events: list[str] = []
    document = FakeDocument(events)
    collab, _api = collaborators(document, events)
    result = run_common_volume_along_path(collab, "Doc", "", ["Wall"])
    assert result["success"] is False
    assert result["error_code"] == "INVALID_ARGUMENT"
    assert "recompute" not in events
    assert "commit" not in events


def test_missing_document_is_rejected():
    events: list[str] = []
    collab, _api = collaborators(None, events)
    result = run_common_volume_along_path(
        collab,
        "Doc",
        "Mover",
        ["Wall"],
        None,
        2,
        [{"x": 0, "y": 0, "z": 0}],
    )
    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"


def test_missing_object_is_rejected():
    events: list[str] = []
    document = FakeDocument(events)
    collab, _api = collaborators(document, events)
    result = run_common_volume_along_path(collab, "Doc", "Mover", ["Wall"])
    assert result["success"] is False
    assert result["error_code"] == "OBJECT_NOT_FOUND"


def test_common_volume_along_path_has_typed_rpc_handler():
    assert subject.TYPED_RPC_HANDLER[0] == "common_volume_along_path"
    assert callable(subject.TYPED_RPC_HANDLER[1])
