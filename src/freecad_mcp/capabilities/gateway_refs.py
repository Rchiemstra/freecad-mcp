"""Gateway dispatch references for bootstrapped manifests."""

from __future__ import annotations

GATEWAY_METHODS = frozenset(
    {
        "finalize_document_edit",
        "save_document",
        "save_document_as",
        "save_document_copy",
    }
)

__all__ = ["GATEWAY_METHODS"]
