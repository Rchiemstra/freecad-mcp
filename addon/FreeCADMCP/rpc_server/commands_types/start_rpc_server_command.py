"""Start RPC Server workbench command."""


class StartRPCServerCommand:
    def GetResources(self):
        return {"MenuText": "Start RPC Server", "ToolTip": "Start RPC Server"}

    def Activated(self):
        from .. import (
            commands,
            rpc_server,  # late import: avoids circular at module load
        )
        msg = rpc_server.start_rpc_server()
        commands.FreeCAD.Console.PrintMessage(msg + "\n")

    def IsActive(self):
        return True
