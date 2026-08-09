import sys as _sys
import os as _os

try:
    _addon_dir = _os.path.dirname(_os.path.abspath(__file__))
except NameError:
    import inspect as _inspect

    _addon_dir = _os.path.dirname(
        _os.path.abspath(_inspect.getfile(_inspect.currentframe()))
    )
if _addon_dir not in _sys.path:
    _sys.path.insert(0, _addon_dir)


class FreeCADMCPAddonWorkbench(Workbench):
    MenuText = "MCP Addon"
    ToolTip = "Addon for MCP Communication"

    def Initialize(self):
        from rpc_server import rpc_server

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


Gui.addWorkbench(FreeCADMCPAddonWorkbench())


def _auto_start_mcp():
    try:
        from rpc_server import rpc_server

        settings = rpc_server.load_settings()
        if not settings.get("auto_start_rpc", False):
            return

        msg = rpc_server.start_rpc_server()
        FreeCAD.Console.PrintMessage(f"[MCP] Auto-start: {msg}\n")
    except Exception as e:
        FreeCAD.Console.PrintWarning(f"[MCP] Auto-start failed: {e}\n")


from PySide import QtCore

QtCore.QTimer.singleShot(0, _auto_start_mcp)


_document_lease_runtime_shutdown_connected = False


def _connect_document_lease_runtime_shutdown(rpc_server):
    global _document_lease_runtime_shutdown_connected
    app = QtCore.QCoreApplication.instance()
    if app is None or _document_lease_runtime_shutdown_connected:
        return
    app.aboutToQuit.connect(rpc_server.shutdown_document_lease_runtime)
    _document_lease_runtime_shutdown_connected = True


def _initialize_document_lease_runtime():
    """Start process-lifetime identity/status even when RPC auto-start is off."""

    try:
        from rpc_server import rpc_server

        rpc_server.initialize_document_lease_runtime()
        _connect_document_lease_runtime_shutdown(rpc_server)
    except Exception as e:
        FreeCAD.Console.PrintWarning(
            f"[MCP] Document lease runtime not initialized: {e}\n"
        )


QtCore.QTimer.singleShot(0, _initialize_document_lease_runtime)


def _register_git_sidecar_observer():
    try:
        from git_sidecar import register_observer

        register_observer()
    except Exception as e:
        FreeCAD.Console.PrintWarning(
            f"[MCP] Git sidecar observer not registered: {e}\n"
        )


QtCore.QTimer.singleShot(0, _register_git_sidecar_observer)


_document_lease_shutdown_connected = False


def _register_document_lease_observer():
    """Install the v2 observer independently of RPC auto-start ordering."""
    global _document_lease_shutdown_connected
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

        _connect_document_lease_runtime_shutdown(rpc_server)
        app = QtCore.QCoreApplication.instance()
        if app is not None and not _document_lease_shutdown_connected:
            app.aboutToQuit.connect(unregister_observer)
            _document_lease_shutdown_connected = True
    except Exception as e:
        FreeCAD.Console.PrintWarning(
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
        FreeCAD.Console.PrintWarning(
            f"[MCP] Document lock feature not registered: {e}\n"
        )


QtCore.QTimer.singleShot(0, _register_document_lock)
