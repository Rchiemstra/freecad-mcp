"""apply_yaw must accept both camera-orientation return types."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.view_manager_ops import focus_helpers

pytestmark = pytest.mark.unit


class _Rotation:
    def __init__(self, *args):
        self.args = args

    def __mul__(self, other):
        return _Rotation("product", self, other)

    @property
    def Q(self):
        return (0.0, 0.0, 0.0, 1.0)


def _fake_freecad(warnings):
    return SimpleNamespace(
        Rotation=_Rotation,
        Vector=lambda *xyz: xyz,
        Console=SimpleNamespace(PrintWarning=warnings.append),
    )


class _View:
    def __init__(self, orientation):
        self.orientation = orientation
        self.set_to = None

    def getCameraOrientation(self):
        return self.orientation

    def setCameraOrientation(self, q):
        self.set_to = q


@pytest.mark.parametrize(
    "orientation",
    [_Rotation((0.0, 0.0, 0.0, 1.0)), (0.0, 0.0, 0.0, 1.0)],
    ids=["rotation", "quaternion-tuple"],
)
def test_apply_yaw_sets_camera_without_warning(monkeypatch, orientation) -> None:
    warnings: list[str] = []
    monkeypatch.setattr(focus_helpers, "FreeCAD", _fake_freecad(warnings))
    view = _View(orientation)

    focus_helpers.apply_yaw(view, 150)

    assert warnings == []
    assert view.set_to == (0.0, 0.0, 0.0, 1.0)


def test_apply_yaw_none_leaves_camera_alone(monkeypatch) -> None:
    warnings: list[str] = []
    monkeypatch.setattr(focus_helpers, "FreeCAD", _fake_freecad(warnings))
    view = _View(_Rotation())

    focus_helpers.apply_yaw(view, None)

    assert view.set_to is None and warnings == []
