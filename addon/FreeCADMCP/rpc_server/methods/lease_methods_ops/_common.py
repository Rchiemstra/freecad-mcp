"""Shared runtime access for lease method modules."""

import logging

try:
    from document_state import document_modified_or_dirty, require_document_modified
except ImportError:
    from addon.FreeCADMCP.document_state import (
        document_modified_or_dirty,
        require_document_modified,
    )

logger = logging.getLogger(__name__)


def _rpc_mod():
    from ... import rpc_server as rpc_mod

    return rpc_mod


__all__ = [
    "_rpc_mod",
    "document_modified_or_dirty",
    "logger",
    "require_document_modified",
]
