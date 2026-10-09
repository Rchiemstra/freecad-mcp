"""Exports into a directory that does not exist must say so.

The staged ``<name>.tmp.<ext>`` file could not be opened and the caller read
"Cannot open file: : /missing/part.tmp.step" from OpenCASCADE.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import measure_io_actions
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.export_brep import run_export_brep
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.export_step import run_export_step
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.export_stl import run_export_stl
from tests.typed_rpc_fakes import FakeDocument, FakeObject, collaborators

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "action, run",
    [
        ("export_step", lambda collab, path: run_export_step(collab, "Doc", path)),
        ("export_stl", lambda collab, path: run_export_stl(collab, "Doc", path)),
        ("export_brep", lambda collab, path: run_export_brep(collab, "Doc", "Box", path)),
    ],
)
def test_a_missing_destination_directory_is_named(tmp_path: Path, action, run):
    events: list[str] = []
    document = FakeDocument(events)
    document.objects["Box"] = FakeObject("Box")
    collab, _api = collaborators(document, events)
    missing = tmp_path / "missing"

    with patch.object(measure_io_actions, action) as exporter:
        result = run(collab, str(missing / "part.out"))

    assert result["success"] is False
    assert result["error_code"] == "DIRECTORY_NOT_FOUND"
    assert f"Directory does not exist: {missing}" in result["error"]
    exporter.assert_not_called()
