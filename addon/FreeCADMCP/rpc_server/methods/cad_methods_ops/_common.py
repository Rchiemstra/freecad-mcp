"""Shared runtime access for CAD method modules."""

try:
    from document_state import require_document_modified
except ImportError:
    from addon.FreeCADMCP.document_state import require_document_modified


__all__ = ["require_document_modified"]
