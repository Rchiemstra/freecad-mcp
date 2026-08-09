try:
    from addon.FreeCADMCP import document_lock as repository_layout
    from FreeCADMCP import document_lock as installed_layout
except ImportError:
    repository_layout = installed_layout = None
