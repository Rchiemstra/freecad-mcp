from importlib import import_module as load_module


def add_constraint(request):
    server = load_module("addon.FreeCADMCP.rpc_server.rpc_server")
    return server.invoke(request)
