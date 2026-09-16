"""Unit coverage for the typed ``export_step`` external-effect slice."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import measure_io_actions
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.export_step import run_export_step
from tests.typed_rpc_fakes import FakeDocument, collaborators

pytestmark = pytest.mark.unit


def test_export_step_publishes_via_atomic_replace(tmp_path: Path):
    events: list[str] = []
    document = FakeDocument(events)
    collab, _api = collaborators(document, events)
    dest = tmp_path / "part.step"

    def _export(_doc, path, _obj_names):
        Path(path).write_text("STEP", encoding="utf-8")
        return {"path": str(dest), "exported": 1}

    with patch.object(measure_io_actions, "export_step", side_effect=_export):
        result = run_export_step(collab, "Doc", str(dest))

    assert result["success"] is True
    assert result["outcome"] == "published"
    assert result["path"] == str(dest)
    assert dest.is_file()
    assert not (tmp_path / "part.tmp.step").exists()
    assert "commit" not in events


def test_missing_document_is_rejected(tmp_path: Path):
    events: list[str] = []
    collab, _api = collaborators(None, events)

    result = run_export_step(collab, "Doc", str(tmp_path / "part.step"))

    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"
