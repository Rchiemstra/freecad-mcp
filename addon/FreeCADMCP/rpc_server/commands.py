"""Qt Command classes for the MCP Addon workbench menu.

Defines the five toolbar/menu entries (Start, Stop, Toggle Auto-Start,
Toggle Remote, Configure Allowed IPs), plus the post-startup sync that
reflects saved settings on the checkable items.

``register_commands()`` and ``schedule_toggle_sync()`` are invoked from
``rpc_server.py`` at import time to preserve current side-effect behavior.
"""

import FreeCAD  # noqa: F401 - §3.3 shim for legacy monkeypatch surface
import FreeCADGui
from PySide import QtCore, QtWidgets

from .commands_types.configure_allowed_ips_command import ConfigureAllowedIPsCommand
from .commands_types.dependencies import (
    CommandDependencies,
    bind_command_dependencies,
    current_command_dependencies,
)
from .commands_types.start_rpc_server_command import StartRPCServerCommand
from .commands_types.stop_rpc_server_command import StopRPCServerCommand
from .commands_types.toggle_auto_start_command import ToggleAutoStartCommand
from .commands_types.toggle_remote_connections_command import (
    ToggleRemoteConnectionsCommand,
)
from .settings import load_settings, save_settings  # noqa: F401 - §3.3 shims


def register_commands(dependencies: CommandDependencies | None = None) -> None:
    if dependencies is not None:
        bind_command_dependencies(dependencies)
    dependencies = current_command_dependencies()
    FreeCADGui.addCommand("Start_RPC_Server", StartRPCServerCommand(dependencies))
    FreeCADGui.addCommand("Stop_RPC_Server", StopRPCServerCommand(dependencies))
    FreeCADGui.addCommand("Toggle_Auto_Start", ToggleAutoStartCommand(dependencies))
    FreeCADGui.addCommand(
        "Toggle_Remote_Connections",
        ToggleRemoteConnectionsCommand(dependencies),
    )
    FreeCADGui.addCommand(
        "Configure_Allowed_IPs",
        ConfigureAllowedIPsCommand(dependencies),
    )


# Map command objectName -> settings key. Matching on objectName rather than
# the localized menu text keeps this working under translation.
_TOGGLE_COMMANDS = {
    "Toggle_Remote_Connections": "remote_enabled",
    "Toggle_Auto_Start": "auto_start_rpc",
}
_SYNC_MAX_RETRIES = 10  # ~20 s at 2 s/retry before giving up


def _sync_toggle_states(retries_left: int = _SYNC_MAX_RETRIES) -> None:
    """Sync checkable menu items with saved settings on startup.

    The menu actions are created asynchronously, so retry a bounded number of
    times until they exist rather than polling forever.
    """
    try:
        settings = load_settings()
        main_window = FreeCADGui.getMainWindow()
        found = 0
        for action in main_window.findChildren(QtWidgets.QAction):
            key = _TOGGLE_COMMANDS.get(action.objectName())
            if key is not None:
                action.setChecked(bool(settings.get(key, False)))
                found += 1
        if found == len(_TOGGLE_COMMANDS):
            return
    except Exception:
        pass
    if retries_left > 0:
        QtCore.QTimer.singleShot(2000, lambda: _sync_toggle_states(retries_left - 1))


def schedule_toggle_sync() -> None:
    QtCore.QTimer.singleShot(2000, _sync_toggle_states)
