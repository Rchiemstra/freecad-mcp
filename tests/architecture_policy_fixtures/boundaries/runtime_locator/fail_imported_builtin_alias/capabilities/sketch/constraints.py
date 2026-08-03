from builtins import __import__ as load


def locate_runtime():
    return load("addon.FreeCADMCP.rpc_server.rpc_server", fromlist=["rpc_server"])
