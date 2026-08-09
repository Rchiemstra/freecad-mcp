def locate_runtime():
    return __import__("addon.FreeCADMCP.rpc_server.rpc_server", fromlist=["rpc_server"])
