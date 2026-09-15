"""Unit coverage for the typed ``export_brep`` external-effect slice."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import measure_io_actions
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.export_brep import run_export_brep
from tests.typed_rpc_fakes import FakeDocument, FakeObject, collaborators

pytestmark = pytest.mark.unit


def test_export_brep_publishes_via_atomic_replace(tmp_path: Path):
    events: list[str] = []
    document = FakeDocument(events)
    document.objects["Box"] = FakeObject("Box")
    collab, _api = collaborators(document, events)
    dest = tmp_path / "part.brep"

    def _export(_doc, _obj_name, path):
        Path(path).write_text("BREP", encoding="utf-8")
        return {"path": str(dest)}

    with patch.object(measure_io_actions, "export_brep", side_effect=_export):
        result = run_export_brep(collab, "Doc", "Box", str(dest))

    assert result["success"] is True
    assert result["outcome"] == "published"
    assert result["path"] == str(dest)
    assert result["object"] == "Box"
    assert dest.is_file()


def test_missing_object_is_rejected(tmp_path: Path):
    events: list[str] = []
    document = FakeDocument(events)
    collab, _api = collaborators(document, events)

    result = run_export_brep(collab, "Doc", "Box", str(tmp_path / "part.brep"))

    assert result["success"] is False
    assert result["error_code"] == "OBJECT_NOT_FOUND"
