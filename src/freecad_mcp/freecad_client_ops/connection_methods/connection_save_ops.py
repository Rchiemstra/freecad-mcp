"""Declarative shim — generated connection method lives in generated/capabilities."""

from freecad_mcp.generated.capabilities.connection_methods import (
    connection_save_ops as _generated,
)

save_document = _generated.save_document
save_document_as = _generated.save_document_as
finalize_document_edit = _generated.finalize_document_edit
release_document_lock = _generated.release_document_lock
force_release_stale_lock = _generated.force_release_stale_lock

__all__ = [  # noqa: RUF022
    'save_document',
    'save_document_as',
    'finalize_document_edit',
    'release_document_lock',
    'force_release_stale_lock',
]
