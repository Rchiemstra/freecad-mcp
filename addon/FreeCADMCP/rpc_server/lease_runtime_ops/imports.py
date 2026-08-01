"""Document lease and lock import helpers for both addon layouts."""

from __future__ import annotations


def import_document_lock():
    """Import document_lock under FreeCAD (addon on path) or unit-test package path."""
    try:
        import document_lock as mod

        return mod
    except ImportError:
        from addon.FreeCADMCP import document_lock as mod

        return mod


def import_document_lease():
    """Import the FreeCAD-independent lease-v2 package in both addon layouts."""
    try:
        # Prefer the repository/package spelling when it is importable. Tests
        # may also place the addon directory directly on sys.path; selecting
        # the top-level spelling first would create duplicate FileBaseline and
        # LeaseCredential classes whose isinstance checks depend on test order.
        from addon.FreeCADMCP import document_lease as mod

        return mod
    except ImportError:
        import document_lease as mod

        return mod
