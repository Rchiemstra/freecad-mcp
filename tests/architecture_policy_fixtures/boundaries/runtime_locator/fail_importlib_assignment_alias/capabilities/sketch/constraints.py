import importlib

load = importlib.import_module


def locate_runtime():
    return load("addon.FreeCADMCP.rpc_server.rpc_server")
