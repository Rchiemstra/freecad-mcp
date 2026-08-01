"""Stop RPC Server workbench command."""


class StopRPCServerCommand:
    def GetResources(self):
        return {"MenuText": "Stop RPC Server", "ToolTip": "Stop RPC Server"}

    def Activated(self):
        from .. import commands, rpc_server
        msg = rpc_server.stop_rpc_server()
        commands.FreeCAD.Console.PrintMessage(msg + "\n")

    def IsActive(self):
        return True
