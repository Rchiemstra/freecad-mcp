from addon.FreeCADMCP.capabilities.fem.meshes import create_mesh
from addon.FreeCADMCP.capabilities.sketch.constraints import add_constraint


def dispatch(request):
    return add_constraint(request), create_mesh(request)
