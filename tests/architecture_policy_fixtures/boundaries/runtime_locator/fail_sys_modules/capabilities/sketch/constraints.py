import sys


def add_constraint(request):
    return sys.modules.get("addon.FreeCADMCP.rpc_server.rpc_server").invoke(request)
