import os as _os
import sys as _sys

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
        FreeCAD.Console.PrintWarning(f"[MCP] Auto-start failed: {e}\n")  # noqa: F821


QtCore.QTimer.singleShot(0, _auto_start_mcp)


_document_lease_runtime_shutdown_state = {"connected": False}


def _connect_document_lease_runtime_shutdown(
    rpc_server,
    _qt_core=QtCore,
    _state=_document_lease_runtime_shutdown_state,
):
    """Connect shutdown without relying on InitGui's execution globals.

    FreeCAD can execute InitGui.py with separate global and local mappings.
    Delayed Qt callbacks therefore need their helpers and mutable state bound
    directly instead of resolving names through the script globals.
    """

    app = _qt_core.QCoreApplication.instance()
    if app is None or _state["connected"]:
        return
    app.aboutToQuit.connect(rpc_server.shutdown_document_lease_runtime)
    _state["connected"] = True


def _initialize_document_lease_runtime(
    _connect_shutdown=_connect_document_lease_runtime_shutdown,
):
    """Start process-lifetime identity/status even when RPC auto-start is off."""

    try:
        from rpc_server import rpc_server

        rpc_server.initialize_document_lease_runtime()
        _connect_shutdown(rpc_server)
    except Exception as e:
        FreeCAD.Console.PrintWarning(  # noqa: F821
            f"[MCP] Document lease runtime not initialized: {e}\n"
        )


QtCore.QTimer.singleShot(0, _initialize_document_lease_runtime)


def _register_git_sidecar_observer():
    try:
        from git_sidecar import register_observer

        register_observer()
    except Exception as e:
        FreeCAD.Console.PrintWarning(  # noqa: F821
            f"[MCP] Git sidecar observer not registered: {e}\n"
        )


QtCore.QTimer.singleShot(0, _register_git_sidecar_observer)


_document_lease_shutdown_state = {"connected": False}


def _register_document_lease_observer(
    _connect_shutdown=_connect_document_lease_runtime_shutdown,
    _qt_core=QtCore,
    _shutdown_state=_document_lease_shutdown_state,
):
    """Install the v2 observer independently of RPC auto-start ordering."""
    try:
        from document_lease.observer import register_observer, unregister_observer

        def _refresh_indicator(_event):
            try:
                from lock_indicator import refresh_lock_indicator

                refresh_lock_indicator()
            except Exception:
                pass

        observer = register_observer(notification_callback=_refresh_indicator)
        if observer is None:
            return
        from rpc_server import rpc_server

        _connect_shutdown(rpc_server)
        app = _qt_core.QCoreApplication.instance()
        if app is not None and not _shutdown_state["connected"]:
            app.aboutToQuit.connect(unregister_observer)
            _shutdown_state["connected"] = True
    except Exception as e:
        FreeCAD.Console.PrintWarning(  # noqa: F821
            f"[MCP] Document lease observer not registered: {e}\n"
        )


# Register the v2 observer before the compatibility observer.  On an
# unexpected close this ensures the active credential is fenced and its v2
# sidecar retained before legacy cleanup callbacks are considered.
QtCore.QTimer.singleShot(0, _register_document_lease_observer)


def _register_document_lock():
    try:
        from document_lock import register_lock_feature

        register_lock_feature()
    except Exception as e:
        FreeCAD.Console.PrintWarning(  # noqa: F821
            f"[MCP] Document lock feature not registered: {e}\n"
        )


QtCore.QTimer.singleShot(0, _register_document_lock)
