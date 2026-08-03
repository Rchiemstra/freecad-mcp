from addon.FreeCADMCP import transport


def invoke(request):
    return transport.listen(request)
