"""Integration check that risky code never reaches the Qt GUI queue."""

from __future__ import annotations

import FreeCADGui


# The conda FreeCAD test package is headless and omits GUI command registration.
if not hasattr(FreeCADGui, "addCommand"):
    FreeCADGui.addCommand = lambda *_args, **_kwargs: None

from addon.FreeCADMCP.rpc_server import rpc_server


class _QueueMustNotBeUsed:
    def put(self, _task):
        raise AssertionError("risky payload was queued on FreeCAD's GUI thread")


def test_transformed_symmetric_difference_is_blocked_before_gui_queue(monkeypatch):
    monkeypatch.setattr(rpc_server, "rpc_request_queue", _QueueMustNotBeUsed())
    code = r'''
def mirrorY(shape, matrix):
    return shape.transformGeometry(matrix)
spm = mirrorY(sp, matrix)
dif = sp.cut(spm).Volume + spm.cut(sp).Volume
dif2 = ghm.cut(gm).Volume + gm.cut(ghm).Volume
'''
    result = rpc_server.FreeCADRPC().execute_code(code, {"read_only": True})
    assert result["success"] is False
    assert result["blocked"] == "gui_thread_boolean_audit"
    assert "Blocked before execution" in result["error"]
