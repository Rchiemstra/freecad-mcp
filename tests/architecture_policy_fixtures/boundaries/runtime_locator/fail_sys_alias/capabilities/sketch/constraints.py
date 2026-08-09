import sys as module_registry


def add_constraint(request):
    server = module_registry.modules.get("addon.FreeCADMCP.rpc_server.rpc_server")
    return server.invoke(request)
