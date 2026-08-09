try:
    import document_lock as direct

    def helper():
        from addon.FreeCADMCP import document_lock as packaged

        return packaged
except ImportError:
    direct = None
