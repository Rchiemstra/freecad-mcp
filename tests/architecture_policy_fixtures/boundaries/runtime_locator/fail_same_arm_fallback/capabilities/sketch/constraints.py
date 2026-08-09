try:
    import document_lock as direct
    from addon.FreeCADMCP import document_lock as packaged
except ImportError:
    direct = packaged = None
