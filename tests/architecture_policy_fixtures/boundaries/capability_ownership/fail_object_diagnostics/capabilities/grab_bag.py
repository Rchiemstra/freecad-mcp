from addon.FreeCADMCP.capabilities.diagnostics.health import inspect_health
from addon.FreeCADMCP.capabilities.object.properties import get_property


def inspect_object(value):
    return get_property(value), inspect_health(value)
