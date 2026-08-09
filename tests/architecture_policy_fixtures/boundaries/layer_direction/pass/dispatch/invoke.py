from addon.FreeCADMCP.capabilities.sketch.constraints import add_constraint
from freecad_mcp.capabilities.sketch.constraints import add_constraint as client_constraint

json_module = __import__("json")
client_capability = __import__("freecad_mcp.capabilities.sketch.constraints")


def invoke(request):
    return add_constraint(request.document, request.constraint)
