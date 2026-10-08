"""set_section_view must reject malformed vectors before touching the GUI.

base=[1, 2] and normal=[1, 0, 0, 9] reached FreeCAD.Vector and came back as the
raw "Either three floats, tuple or Vector expected".
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.methods.gui_methods_ops import gui_interaction

pytestmark = pytest.mark.unit


def _facade():
    def fail(*_args, **_kwargs):
        raise AssertionError("invalid arguments must not reach the GUI")

    return SimpleNamespace(_gui_collaborators=SimpleNamespace(set_section_view=fail))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"base": [1, 2]},
        {"normal": [1, 0, 0, 9]},
        {"normal": [0, 0, 0]},
        {"base": [0, "x", 0]},
        {"normal": [float("nan"), 0, 1]},
    ],
)
def test_malformed_section_vectors_are_invalid_arguments(kwargs, monkeypatch):
    monkeypatch.setattr(gui_interaction, "request_actor", lambda _self: "actor")

    result = gui_interaction.set_section_view(_facade(), enabled=True, **kwargs)

    assert result["ok"] is False
    assert result["error_code"] == "INVALID_ARGUMENT"
