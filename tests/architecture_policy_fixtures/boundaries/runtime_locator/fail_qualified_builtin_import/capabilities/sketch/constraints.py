import builtins


def locate_runtime():
    return builtins.__import__(
        "addon.FreeCADMCP.rpc_server.rpc_server", fromlist=["rpc_server"]
    )
