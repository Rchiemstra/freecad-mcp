"""Shared runtime access for CAD method modules."""

try:
    from document_state import require_document_modified
except ImportError:
    from addon.FreeCADMCP.document_state import require_document_modified


def _rpc_mod():
    from ... import rpc_server as rpc_mod

    return rpc_mod


__all__ = ["_rpc_mod", "require_document_modified"]
