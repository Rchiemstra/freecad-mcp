"""Auto-start RPC server toggle workbench command."""

from .dependencies import CommandDependencies, current_command_dependencies


class ToggleAutoStartCommand:
    def __init__(self, dependencies: CommandDependencies | None = None) -> None:
        self._dependencies = dependencies or current_command_dependencies()

    def GetResources(self):
        return {
            "MenuText": "Auto-Start Server",
            "ToolTip": "Automatically start the RPC server when FreeCAD launches.",
            "Checkable": True,
        }

    def Activated(self, checked=0):
        settings = self._dependencies.load_settings()
        settings["auto_start_rpc"] = bool(checked)
        self._dependencies.save_settings(settings)

        if settings["auto_start_rpc"]:
            self._dependencies.freecad.Console.PrintMessage(
                "MCP RPC server will start automatically on next FreeCAD launch.\n"
            )
        else:
            self._dependencies.freecad.Console.PrintMessage(
                "MCP RPC server auto-start disabled.\n"
            )

    def IsActive(self):
        return True
