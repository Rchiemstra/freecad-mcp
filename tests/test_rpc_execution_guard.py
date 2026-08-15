"""Integration check that risky code never reaches the Qt GUI queue."""

from __future__ import annotations

import FreeCADGui
import os
from pathlib import Path
from unittest.mock import MagicMock


# The conda FreeCAD test package is headless and omits GUI command registration.
if not hasattr(FreeCADGui, "addCommand"):
    FreeCADGui.addCommand = lambda *_args, **_kwargs: None

from addon.FreeCADMCP.rpc_server import rpc_server
from freecad_mcp.operations.p7_assembly import (
    sketch_add_external_projection_operation,
)
from tests.helpers.native_readiness import attach_native_readiness


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

ISINSIDE_GRID_CODE = r'''
for radius in radii:
    for index in range(720):
        point = points[radius, index]
        samples.append(shape.isInside(point, 1e-4, True))
'''


class _DispatcherMustNotBeUsed:
    def submit(self, *_args, **_kwargs):
        raise AssertionError("risky payload was dispatched to FreeCAD's GUI thread")


def _external_projection_payload(*, allow_gui_geometry_loop):
    connection = MagicMock()
    connection.get_active_screenshot.return_value = None
    connection.execute_code.return_value = {
        "success": False,
        "error": "capture only",
    }
    sketch_add_external_projection_operation(
        connection,
        True,
        "Doc",
        "Sketch",
        "Binder:Face1",
        allow_gui_geometry_loop=allow_gui_geometry_loop,
    )
    code, options = connection.execute_code.call_args[0]
    return code, options.to_dict()


def test_external_projection_default_is_blocked_by_actual_loop_guard():
    connection = MagicMock()
    connection.get_active_screenshot.return_value = None
    result = sketch_add_external_projection_operation(
        connection,
        True,
        "Doc",
        "Sketch",
        "Binder:Face1",
        allow_gui_geometry_loop=False,
    )

    connection.execute_code.assert_not_called()
    envelope = result.structuredContent
    assert envelope["status"] == "failed"
    assert envelope["error_code"] == "gui_geometry_loop_opt_in_required"
    assert "allow_gui_geometry_loop=true" in envelope["error"]


def test_external_projection_explicit_override_reaches_gui_dispatch():
    code, options = _external_projection_payload(allow_gui_geometry_loop=True)
    rpc = rpc_server.FreeCADRPC()
    dispatched = {}

    def fake_dispatch_gui(task, timeout):
        dispatched["called"] = True
        dispatched["timeout"] = timeout
        return {"ok": True, "session": {}, "stdout": ""}

    rpc._dispatch_gui = fake_dispatch_gui
    result = rpc.execute_code(code, options)

    assert options["execution_mode"] == "gui"
    assert options["allow_gui_geometry_loop"] is True
    assert result["success"] is True
    assert dispatched["called"] is True


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


def test_isinside_grid_is_blocked_before_gui_queue(monkeypatch):
    monkeypatch.setattr(rpc_server, "gui_dispatcher", _DispatcherMustNotBeUsed())
    result = rpc_server.FreeCADRPC().execute_code(ISINSIDE_GRID_CODE)
    assert result["success"] is False
    assert result["blocked"] == "gui_thread_geometry_loop"
    assert "Worker-only geometry loops" in result["error"]
    assert "execution_mode='worker'" in result["error"]


def test_isinside_grid_cannot_use_gui_override(monkeypatch):
    """The escape hatch must not admit the read-only gear sampling incident."""
    monkeypatch.setattr(rpc_server, "gui_dispatcher", _DispatcherMustNotBeUsed())
    result = rpc_server.FreeCADRPC().execute_code(
        ISINSIDE_GRID_CODE,
        {"execution_mode": "gui", "allow_gui_geometry_loop": True},
    )
    assert result["success"] is False
    assert result["blocked"] == "gui_thread_geometry_loop"
    assert "cannot use the GUI override" in result["error"]


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


def test_execute_code_saved_flag_matches_disk(tmp_path, monkeypatch):
    model = tmp_path / "Model.FCStd"
    model.write_bytes(b"before")
    before_mtime = model.stat().st_mtime_ns

    class _Document:
        Name = "Model"
        FileName = str(model)
        Modified = True
        Objects = []

        def save(self):
            model.write_bytes(b"saved content with a different size")
            os.utime(model, ns=(before_mtime + 1_000_000, before_mtime + 1_000_000))
            self.Modified = False

        def commitCompatibilityMutation(
            self,
            callback,
            *,
            structural=False,
            recompute=True,
            postcondition=None,
            trusted_structural=False,
        ):
            assert structural is True
            assert recompute is False
            assert postcondition is None
            assert trusted_structural is True
            callback()
            return {
                "status": "Committed",
                "committed": True,
                "revisions": {"UnknownModel": 1},
            }

    document = attach_native_readiness(_Document())
    monkeypatch.setattr(
        rpc_server.FreeCAD, "listDocuments", lambda: {document.Name: document}
    )
    monkeypatch.setattr(
        rpc_server.FreeCAD,
        "getDocument",
        lambda name: document if name == document.Name else None,
    )
    monkeypatch.setattr(rpc_server.FreeCAD, "ActiveDocument", document)
    rpc = rpc_server.FreeCADRPC()
    monkeypatch.setattr(rpc, "_collect_invalid_objects", lambda: {})
    monkeypatch.setattr(rpc, "_dispatch_gui", lambda task, _timeout: task())

    result = rpc.execute_code(
        "FreeCAD.getDocument('Model').save()",
        {"document": "Model", "execution_mode": "gui"},
    )

    assert result["success"] is True
    assert model.stat().st_mtime_ns > before_mtime
    assert result["session"]["saved"] is True
    assert result["session"]["saved_documents"] == ["Model"]
