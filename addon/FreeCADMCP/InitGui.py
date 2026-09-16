import os as _os
import sys as _sys
from functools import partial as _partial

from PySide import QtCore

# FreeCAD injects FreeCAD, Gui, and Workbench into InitGui's namespace at load
# time. Do not import them here — that breaks FreeCAD's InitGui exec model and
# the split-exec test harness (F821 names are intentional; noqa where used).

try:
    _addon_dir = _os.path.dirname(_os.path.abspath(__file__))
except NameError:
    import inspect as _inspect

    _addon_dir = _os.path.dirname(
        _os.path.abspath(_inspect.getfile(_inspect.currentframe()))
    )
if _addon_dir not in _sys.path:
    _sys.path.insert(0, _addon_dir)


class FreeCADMCPAddonWorkbench(Workbench):  # noqa: F821
    MenuText = "MCP Addon"
    ToolTip = "Addon for MCP Communication"

    def Initialize(self):
        # Import registers workbench commands before toolbar/menu append.
        from rpc_server import rpc_server  # noqa: F401

        commands = [
            "Start_RPC_Server",
            "Stop_RPC_Server",
            "Toggle_Auto_Start",
            "Toggle_Remote_Connections",
            "Configure_Allowed_IPs",
        ]
        self.appendToolbar("FreeCAD MCP", commands)
        self.appendMenu("FreeCAD MCP", commands)

    def Activated(self):
        pass

    def Deactivated(self):
        pass

    def ContextMenu(self, recipient):
        pass

    def GetClassName(self):
        return "Gui::PythonWorkbench"


Gui.addWorkbench(FreeCADMCPAddonWorkbench())  # noqa: F821


def _auto_start_mcp():
    try:
        from rpc_server import rpc_server

        settings = rpc_server.load_settings()
        if not settings.get("auto_start_rpc", False):
            return

        msg = rpc_server.start_rpc_server()
        FreeCAD.Console.PrintMessage(f"[MCP] Auto-start: {msg}\n")  # noqa: F821
    except Exception as e:
        import traceback as _traceback

        FreeCAD.Console.PrintWarning(  # noqa: F821
            f"[MCP] Auto-start failed: {e}\n{_traceback.format_exc()}"
        )


QtCore.QTimer.singleShot(0, _auto_start_mcp)


_rpc_runtime_shutdown_state = {"connected": False, "callback": None}


def _shutdown_mcp_runtime(rpc_server):
    """Stop the adapter graph without changing native document state."""

    rpc_server.stop_rpc_server(wait_for_completion=True)


def _connect_rpc_runtime_shutdown(
    rpc_server,
    _qt_core=QtCore,
    _state=_rpc_runtime_shutdown_state,
    _partial_callback=_partial,
    _shutdown_callback=_shutdown_mcp_runtime,
):
    """Connect shutdown without relying on InitGui's execution globals.

    FreeCAD can execute InitGui.py with separate global and local mappings.
    Delayed Qt callbacks therefore need their helpers and mutable state bound
    directly instead of resolving names through the script globals.
    """

    app = _qt_core.QCoreApplication.instance()
    if app is None or _state["connected"]:
        return
    callback = _partial_callback(_shutdown_callback, rpc_server)
    app.aboutToQuit.connect(callback)
    _state["callback"] = callback
    _state["connected"] = True


def _initialize_rpc_runtime_shutdown(
    _connect_shutdown=_connect_rpc_runtime_shutdown,
):
    """Install deterministic shutdown even when RPC auto-start is off."""

    try:
        from rpc_server import rpc_server

        _connect_shutdown(rpc_server)
    except Exception as e:
        import traceback as _traceback

        FreeCAD.Console.PrintWarning(  # noqa: F821
            f"[MCP] RPC shutdown hook not initialized: {e}\n{_traceback.format_exc()}"
        )


QtCore.QTimer.singleShot(0, _initialize_rpc_runtime_shutdown)


def _register_git_sidecar_observer():
    try:
        from git_sidecar import register_observer

        register_observer()
    except Exception as e:
        FreeCAD.Console.PrintWarning(  # noqa: F821
            f"[MCP] Git sidecar observer not registered: {e}\n"
        )


QtCore.QTimer.singleShot(0, _register_git_sidecar_observer)

