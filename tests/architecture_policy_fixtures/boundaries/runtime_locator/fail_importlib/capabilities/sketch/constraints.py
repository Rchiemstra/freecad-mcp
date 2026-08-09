import importlib as loader


def add_constraint(request):
    server = loader.import_module("addon.FreeCADMCP.rpc_server.rpc_server")
    return server.invoke(request)
