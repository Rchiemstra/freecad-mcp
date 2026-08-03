try:
    from addon.FreeCADMCP import document_lock as document_lock
except ImportError:
    from FreeCADMCP import document_lock as document_lock
