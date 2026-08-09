from addon.FreeCADMCP.dispatch.invoke import invoke


def listen(request):
    return invoke(request)
