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


def test_transformed_symmetric_difference_forced_gui_routes_to_worker(monkeypatch):
    rpc = rpc_server.FreeCADRPC()
    routed = {}

    def worker(code, options):
        routed["code"] = code
        routed["options"] = options
        return {"success": True, "execution": {"mode": "worker"}}

    monkeypatch.setattr(rpc, "_execute_code_worker", worker)
    monkeypatch.setattr(rpc_server, "gui_dispatcher", _DispatcherMustNotBeUsed())
    result = rpc.execute_code(
        HANGING_SYMMETRY_CODE, {"read_only": True, "execution_mode": "gui"}
    )
    assert result["success"] is True
    assert result["execution"]["mode"] == "worker"
    assert routed["code"] == HANGING_SYMMETRY_CODE
    assert routed["options"]["execution_mode"] == "gui"


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


def test_read_only_geometry_sweep_cannot_be_forced_onto_gui(monkeypatch):
    rpc = rpc_server.FreeCADRPC()
    routed = {}

    def worker(code, options):
        routed["code"] = code
        routed["options"] = options
        return {"success": True, "execution": {"mode": "worker"}}

    monkeypatch.setattr(rpc, "_execute_code_worker", worker)
    monkeypatch.setattr(rpc_server, "gui_dispatcher", _DispatcherMustNotBeUsed())
    result = rpc.execute_code(
        SWEEP45_1_CODE,
        {"read_only": True, "execution_mode": "gui"},
    )
    assert result["success"] is True
    assert result["execution"]["mode"] == "worker"
    assert routed["code"] == SWEEP45_1_CODE
    assert routed["options"]["execution_mode"] == "gui"


def test_lightweight_read_only_code_forced_gui_still_routes_to_worker(monkeypatch):
    rpc = rpc_server.FreeCADRPC()
    routed = {}

    def worker(code, options):
        routed["code"] = code
        routed["options"] = options
        return {"success": True, "execution": {"mode": "worker"}}

    monkeypatch.setattr(rpc, "_execute_code_worker", worker)
    monkeypatch.setattr(rpc_server, "gui_dispatcher", _DispatcherMustNotBeUsed())
    result = rpc.execute_code(
        "print(FreeCAD.ActiveDocument.Name)",
        {"read_only": True, "execution_mode": "gui"},
    )
    assert result["success"] is True
    assert result["execution"]["mode"] == "worker"
    assert routed["options"]["read_only"] is True


def test_worker_timeout_is_rejected_for_gui_execution(monkeypatch):
    monkeypatch.setattr(rpc_server, "gui_dispatcher", _DispatcherMustNotBeUsed())
    result = rpc_server.FreeCADRPC().execute_code(
        "print('bounded GUI work')",
        {"execution_mode": "gui", "timeout_seconds": 240},
    )
    assert result["success"] is False
    assert result["error_code"] == "gui_timeout_not_supported"
    assert "cannot safely stop code running on FreeCAD's GUI thread" in result["error"]


def test_forced_gui_geometry_mutation_is_blocked(monkeypatch):
    """The exact 2026-07-22 freeze: gui + read_only=false + geometry loop.

    Previously this bypassed the guard (neither auto-mutation nor
    forced-analysis) and was dispatched to the GUI thread, hanging FreeCAD.
    It must now be blocked before the queue and point at the worker / opt-in.
    """
    monkeypatch.setattr(rpc_server, "gui_dispatcher", _DispatcherMustNotBeUsed())
    result = rpc_server.FreeCADRPC().execute_code(
        SWEEP45_1_CODE,
        {"execution_mode": "gui"},
    )
    assert result["success"] is False
    assert result["blocked"] == "gui_thread_geometry_loop"
    assert "read_only=true" in result["error"]
    assert "execution_mode='worker'" in result["error"]
    assert "allow_gui_geometry_loop=true" in result["error"]


def test_forced_gui_geometry_mutation_optin_reaches_gui(monkeypatch):
    """The explicit escape hatch lets a genuine live mutation run on the GUI."""
    rpc = rpc_server.FreeCADRPC()
    dispatched = {}

    def fake_dispatch_gui(task, timeout):
        dispatched["called"] = True
        dispatched["timeout"] = timeout
        return {"ok": True, "session": {}, "stdout": ""}

    monkeypatch.setattr(rpc, "_dispatch_gui", fake_dispatch_gui)
    result = rpc.execute_code(
        SWEEP45_1_CODE,
        {"execution_mode": "gui", "allow_gui_geometry_loop": True},
    )
    assert result["success"] is True
    assert dispatched.get("called") is True
