from addon.FreeCADMCP.capabilities.export.files import export_file
from addon.FreeCADMCP.capabilities.ui.dialogs import open_dialog


def open_export_dialog(value):
    return open_dialog(value), export_file(value)
