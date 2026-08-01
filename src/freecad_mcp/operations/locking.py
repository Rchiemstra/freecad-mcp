"""Document lock / lease operation wrappers (thin façade; §3.3 shims)."""

from __future__ import annotations

from .locking_ops.acquisition_ops import (
    acquire_document_lock_operation,
    adopt_dirty_document_operation,
    claim_acquisition_result_operation,
)
from .locking_ops.legacy_keys import (
    _legacy_alias,
    forget_legacy_document_key,
    legacy_selector_doc_key,
)
from .locking_ops.lifecycle_ops import (
    force_release_stale_lock_operation,
    get_document_lock_operation,
    heartbeat_document_lock_operation,
    list_document_locks_operation,
    release_document_lock_operation,
    update_document_lock_operation,
)
from .locking_ops.response_helpers import (
    _lock_response,
    _public_acquisition_result,
)
from .locking_ops.store_grant import _store_lease_grant

__all__ = [
    "_legacy_alias",
    "_lock_response",
    "_public_acquisition_result",
    "_store_lease_grant",
    "acquire_document_lock_operation",
    "adopt_dirty_document_operation",
    "claim_acquisition_result_operation",
    "force_release_stale_lock_operation",
    "forget_legacy_document_key",
    "get_document_lock_operation",
    "heartbeat_document_lock_operation",
    "legacy_selector_doc_key",
    "list_document_locks_operation",
    "release_document_lock_operation",
    "update_document_lock_operation",
]
