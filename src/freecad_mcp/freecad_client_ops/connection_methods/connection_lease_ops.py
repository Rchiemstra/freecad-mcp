"""Declarative shim — generated connection method lives in generated/capabilities."""

from freecad_mcp.generated.capabilities.connection_methods import (
    connection_lease_ops as _generated,
)

acquire_document_lock = _generated.acquire_document_lock
adopt_dirty_document = _generated.adopt_dirty_document
get_document_lock = _generated.get_document_lock
list_document_locks = _generated.list_document_locks
heartbeat_document_lock = _generated.heartbeat_document_lock
update_document_lock = _generated.update_document_lock
_legacy_authority_removed = _generated._legacy_authority_removed

__all__ = [  # noqa: RUF022
    'acquire_document_lock',
    'adopt_dirty_document',
    'get_document_lock',
    'list_document_locks',
    'heartbeat_document_lock',
    'update_document_lock',
    '_legacy_authority_removed',
]
