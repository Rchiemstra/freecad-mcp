"""Start RPC Server workbench command."""

from .dependencies import CommandDependencies, current_command_dependencies


class StartRPCServerCommand:
    def __init__(self, dependencies: CommandDependencies | None = None) -> None:
        self._dependencies = dependencies or current_command_dependencies()

    def GetResources(self):
        return {"MenuText": "Start RPC Server", "ToolTip": "Start RPC Server"}

    def Activated(self):
        msg = self._dependencies.start_rpc_server()
        self._dependencies.freecad.Console.PrintMessage(msg + "\n")

    def IsActive(self):
        return True
