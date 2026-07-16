"""Integration check that risky code never reaches the Qt GUI queue."""

from __future__ import annotations

import FreeCADGui
from pathlib import Path


# The conda FreeCAD test package is headless and omits GUI command registration.
if not hasattr(FreeCADGui, "addCommand"):
    FreeCADGui.addCommand = lambda *_args, **_kwargs: None

from addon.FreeCADMCP.rpc_server import rpc_server


HANGING_SYMMETRY_CODE = r'''
def mirrorY(shape, matrix):
    return shape.transformGeometry(matrix)
spm = mirrorY(sp, matrix)
dif = sp.cut(spm).Volume + spm.cut(sp).Volume
dif2 = ghm.cut(gm).Volume + gm.cut(ghm).Volume
'''

SWEEP45_1_CODE = (
    Path(__file__).resolve().parent / "fixtures" / "sweep45_1_payload.py.txt"
).read_text(encoding="utf-8")


class _DispatcherMustNotBeUsed:
    def submit(self, *_args, **_kwargs):
        raise AssertionError("risky payload was dispatched to FreeCAD's GUI thread")


def test_transformed_symmetric_difference_is_blocked_before_gui_queue(monkeypatch):
    monkeypatch.setattr(rpc_server, "gui_dispatcher", _DispatcherMustNotBeUsed())
    result = rpc_server.FreeCADRPC().execute_code(
        HANGING_SYMMETRY_CODE, {"read_only": True, "execution_mode": "gui"}
    )
    assert result["success"] is False
    assert result["blocked"] == "gui_thread_boolean_audit"
    assert "Blocked before execution" in result["error"]


def test_transformed_symmetric_difference_auto_routes_to_worker(monkeypatch):
    rpc = rpc_server.FreeCADRPC()
    routed = {}

    def worker(code, options):
        routed["code"] = code
        routed["options"] = options
        return {"success": True, "execution": {"mode": "worker"}}

    monkeypatch.setattr(rpc, "_execute_code_worker", worker)
    result = rpc.execute_code(
        HANGING_SYMMETRY_CODE,
        {"read_only": True, "execution_mode": "auto"},
    )
    assert result["success"] is True
    assert result["execution"]["mode"] == "worker"
    assert routed["code"] == HANGING_SYMMETRY_CODE


def test_unmarked_geometry_sweep_is_blocked_before_gui_queue(monkeypatch):
    monkeypatch.setattr(rpc_server, "gui_dispatcher", _DispatcherMustNotBeUsed())
    result = rpc_server.FreeCADRPC().execute_code(SWEEP45_1_CODE)
    assert result["success"] is False
    assert result["blocked"] == "gui_thread_geometry_loop"
    assert "read_only=true" in result["error"]
    assert "execution_mode='worker'" in result["error"]


def test_marked_sweep45_1_auto_routes_to_worker(monkeypatch):
    rpc = rpc_server.FreeCADRPC()
    routed = {}

    def worker(code, options):
        routed["code"] = code
        routed["options"] = options
        return {"success": True, "execution": {"mode": "worker"}}

    monkeypatch.setattr(rpc, "_execute_code_worker", worker)
    result = rpc.execute_code(
        SWEEP45_1_CODE,
        {"read_only": True, "execution_mode": "auto", "timeout_seconds": 120},
    )
    assert result["success"] is True
    assert result["execution"]["mode"] == "worker"
    assert routed["code"] == SWEEP45_1_CODE
    assert routed["options"]["timeout_seconds"] == 120
