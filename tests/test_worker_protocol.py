"""Worker protocol limits and unsupported GUI API checks."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import FreeCADGui

if not hasattr(FreeCADGui, "addCommand"):
    FreeCADGui.addCommand = lambda *_args, **_kwargs: None

from addon.FreeCADMCP.rpc_server.worker_protocol import (
    CappedTextWriter,
    ProtocolError,
    reject_detectable_gui_usage,
)
from addon.FreeCADMCP.rpc_server import snapshot_service


def test_stdout_is_capped_while_writing():
    writer = CappedTextWriter(limit=5)
    assert writer.write("abc") == 3
    assert writer.write("defgh") == 5
    assert writer.getvalue() == "abcde"
    assert writer.truncated is True


@pytest.mark.parametrize(
    "code",
    [
        "import FreeCADGui",
        "from FreeCADGui import Selection",
        "Gui.activeDocument()",
        "FreeCAD.Gui.ActiveDocument",
    ],
)
def test_detectable_worker_gui_usage_is_rejected(code):
    with pytest.raises(ProtocolError, match="unsupported"):
        reject_detectable_gui_usage(code)


def test_dynamic_import_is_not_misrepresented_as_a_security_boundary():
    # Static inspection is best effort; the worker also supplies an API-level
    # import guard, but neither mechanism is a security sandbox.
    reject_detectable_gui_usage("__import__('Free' + 'CADGui')")


def test_selection_state_includes_selected_subelements(monkeypatch):
    selection = SimpleNamespace(
        getSelectionEx=lambda: [
            SimpleNamespace(
                DocumentName="Model",
                ObjectName="Box",
                SubElementNames=["Face1", "Edge2"],
            )
        ]
    )
    monkeypatch.setattr(snapshot_service.FreeCADGui, "Selection", selection, raising=False)
    assert snapshot_service._selection_state() == [
        ("Model", "Box", ("Face1", "Edge2"))
    ]
