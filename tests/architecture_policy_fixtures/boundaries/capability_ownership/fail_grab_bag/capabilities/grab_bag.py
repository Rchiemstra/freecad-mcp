from addon.FreeCADMCP.capabilities.fem.meshes import create_mesh
from addon.FreeCADMCP.capabilities.sketch.constraints import add_constraint


def make_everything(document, value):
    return add_constraint(document, value), create_mesh(document, value)
