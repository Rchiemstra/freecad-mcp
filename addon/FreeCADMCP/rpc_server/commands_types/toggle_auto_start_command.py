"""Auto-start RPC server toggle workbench command."""


class ToggleAutoStartCommand:
    def GetResources(self):
        return {
            "MenuText": "Auto-Start Server",
            "ToolTip": "Automatically start the RPC server when FreeCAD launches.",
            "Checkable": True,
        }

    def Activated(self, checked=0):
        from .. import commands
        settings = commands.load_settings()
        settings["auto_start_rpc"] = bool(checked)
        commands.save_settings(settings)

        if settings["auto_start_rpc"]:
            commands.FreeCAD.Console.PrintMessage(
                "MCP RPC server will start automatically on next FreeCAD launch.\n"
            )
        else:
            commands.FreeCAD.Console.PrintMessage(
                "MCP RPC server auto-start disabled.\n"
            )

    def IsActive(self):
        return True
