import sys

registry = sys.modules


def locate_runtime():
    return registry.get("addon.FreeCADMCP.rpc_server.rpc_server")
