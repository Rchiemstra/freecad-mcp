"""Document lease and lock import helpers for both addon layouts."""

from __future__ import annotations

try:
    from addon.FreeCADMCP import document_lease as _document_lease
    from addon.FreeCADMCP import document_lock as _document_lock
except ImportError:  # pragma: no cover - flat FreeCAD addon layout
    import document_lease as _document_lease
    import document_lock as _document_lock


def import_document_lock():
    """Import document_lock under FreeCAD (addon on path) or unit-test package path."""
    return _document_lock


def import_document_lease():
    """Import the FreeCAD-independent lease-v2 package in both addon layouts."""
    return _document_lease
