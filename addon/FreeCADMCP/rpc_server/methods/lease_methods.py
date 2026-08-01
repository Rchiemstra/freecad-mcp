"""Document-lease RPC methods bound on ``FreeCADRPC``."""

from .lease_methods_ops.acquire import acquire_document_lock, adopt_dirty_document
from .lease_methods_ops.acquire_v2 import acquire_document_lock_v2
from .lease_methods_ops.acquisition_claims import (
    acknowledge_acquisition_claim,
    claim_acquisition_result,
)
from .lease_methods_ops.handoff import (
    escrow_locked_error_handoff_claim,
    journal_handoff_terminal,
    run_locked_error_handoff_continuation,
    start_locked_error_handoff_continuation,
)
from .lease_methods_ops.heartbeat import lease_heartbeat_batch
from .lease_methods_ops.lock_query import (
    get_document_lock,
    heartbeat_document_lock,
    list_document_locks,
    update_document_lock,
)
from .lease_methods_ops.reconcile import lease_reconcile
from .lease_methods_ops.release import force_release_stale_lock, release_document_lock
from .lease_methods_ops.save_legacy import run_legacy_save
from .lease_methods_ops.save_public import (
    finalize_document_edit,
    save_document,
    save_document_as,
)
from .lease_methods_ops.save_typed import run_typed_save

__all__ = [
    "acknowledge_acquisition_claim",
    "acquire_document_lock",
    "acquire_document_lock_v2",
    "adopt_dirty_document",
    "claim_acquisition_result",
    "escrow_locked_error_handoff_claim",
    "finalize_document_edit",
    "force_release_stale_lock",
    "get_document_lock",
    "heartbeat_document_lock",
    "journal_handoff_terminal",
    "lease_heartbeat_batch",
    "lease_reconcile",
    "list_document_locks",
    "release_document_lock",
    "run_legacy_save",
    "run_locked_error_handoff_continuation",
    "run_typed_save",
    "save_document",
    "save_document_as",
    "start_locked_error_handoff_continuation",
    "update_document_lock",
]

