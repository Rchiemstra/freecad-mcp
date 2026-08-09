from addon.FreeCADMCP.capabilities.fem.meshes import create_mesh
from addon.FreeCADMCP.capabilities.sketch.constraints import add_constraint
from addon.FreeCADMCP.dispatch.invoke import invoke
from addon.FreeCADMCP.transport.listener import listen


def build_runtime():
    return listen, invoke, add_constraint, create_mesh
