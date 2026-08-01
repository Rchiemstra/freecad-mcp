"""Imported operation callables for DocumentLeaseService class-attribute binding."""

from __future__ import annotations

from .acquiring_reservation import (
    _clear_acquiring_request,
    _is_unreturned_reservation,
    _may_fence_local_active_acquiring,
    _remember_acquiring_request,
    _replace_unreturned_reservation,
)
from .acquisition_complete import (
    _complete_acquisition_record,
    abort_acquisition,
    complete_acquisition,
    complete_dirty_adoption,
    fail_acquisition_after_mutation,
    record_acquisition_snapshot,
)
from .acquisition_entry import (
    acquire,
    begin_acquisition,
    begin_dirty_adoption,
)
from .authorize_ops import authorize, heartbeat, update_metadata
from .begin_acquisition import _begin_acquisition_record
from .document_lifecycle import (
    handle_document_closed,
    rebind_closed_recovery_document,
)
from .effective_records import (
    _clear_effective_error_times,
    _coordination_lost_status,
    _effective_error_at,
    _effective_foreign_public,
    _effective_public_record,
    get_effective,
    list_effective_records,
)
from .foreign_import import (
    confirmed_takeover_foreign_recovery,
    import_adjacent_foreign_recovery,
)
from .foreign_validation import (
    _assert_foreign_document_exact,
    _is_abandoned_locked_error_foreign_candidate,
    _is_clean_orphaned_foreign_candidate,
    _is_missing_sidecar_foreign_recovery_candidate,
    _is_recoverable_local_mcp_orphan_candidate,
    _is_saved_dirty_foreign_candidate,
)
from .identity_refresh import (
    _apply_baseline_preserving_identity_refresh,
    _assert_current_baseline,
    _assert_on_disk_matches_accepted_baseline,
    _record_identity_refresh_event,
    _refresh_exact_proxy_file_identity,
)
from .identity_refresh_public import (
    repair_registered_document_identity,
    try_baseline_preserving_document_identity_refresh,
)
from .live_evidence import _validate_live_evidence
from .local_recovery import (
    acknowledge_local_dirty,
    complete_local_save_and_clear,
)
from .locked_error_handoff import claim_locked_error_handoff
from .mutation_ops import (
    begin_mutation,
    begin_recompute,
    begin_recovery,
    complete_operation,
    record_error,
)
from .orphaned_foreign_begin import begin_orphaned_foreign_acquisition
from .queries import (
    get,
    get_foreign_recovery,
    has_unresolved_owner,
    list_foreign_recoveries,
    list_records,
    refresh_orphaned_foreign_document_identity,
)
from .recover_orphaned_foreign import recover_orphaned_foreign_acquisition
from .recover_orphaned_local import recover_orphaned_local_mcp_acquisition
from .recovery_proofs import (
    _is_misattributed_worker_snapshot_intervention,
    _parse_timestamp,
    _prove_foreign_owner_dead,
    _prove_local_mcp_owner_dead,
    _prove_local_mcp_recovery_authority_inactive,
    _prove_orphaned_foreign_authority_inactive,
)
from .registry_core import _commit, _record_for_credential
from .release_clean import release_clean
from .save_as_ops import commit_save_as, mark_save_verified, reserve_save_as
from .save_cancel import (
    begin_cancellation,
    begin_save,
    cancel_save_before_mutation,
    complete_cancellation,
)
from .saved_foreign_acquisition import begin_saved_foreign_recovery_acquisition
from .sidecar_authority import (
    _assert_sidecar_matches,
    _authority_equal,
    _sidecar_path,
)
from .stale_ops import mark_expired_stale, mark_stale, reconcile_stale
from .takeover_ops import (
    refresh_local_recovery_document_identity,
    takeover,
    update_local_dirty,
)

__all__ = [
    "_apply_baseline_preserving_identity_refresh",
    "_assert_current_baseline",
    "_assert_foreign_document_exact",
    "_assert_on_disk_matches_accepted_baseline",
    "_assert_sidecar_matches",
    "_authority_equal",
    "_begin_acquisition_record",
    "_clear_acquiring_request",
    "_clear_effective_error_times",
    "_commit",
    "_complete_acquisition_record",
    "_coordination_lost_status",
    "_effective_error_at",
    "_effective_foreign_public",
    "_effective_public_record",
    "_is_abandoned_locked_error_foreign_candidate",
    "_is_clean_orphaned_foreign_candidate",
    "_is_misattributed_worker_snapshot_intervention",
    "_is_missing_sidecar_foreign_recovery_candidate",
    "_is_recoverable_local_mcp_orphan_candidate",
    "_is_saved_dirty_foreign_candidate",
    "_is_unreturned_reservation",
    "_may_fence_local_active_acquiring",
    "_parse_timestamp",
    "_prove_foreign_owner_dead",
    "_prove_local_mcp_owner_dead",
    "_prove_local_mcp_recovery_authority_inactive",
    "_prove_orphaned_foreign_authority_inactive",
    "_record_for_credential",
    "_record_identity_refresh_event",
    "_refresh_exact_proxy_file_identity",
    "_remember_acquiring_request",
    "_replace_unreturned_reservation",
    "_sidecar_path",
    "_validate_live_evidence",
    "abort_acquisition",
    "acknowledge_local_dirty",
    "acquire",
    "authorize",
    "begin_acquisition",
    "begin_cancellation",
    "begin_dirty_adoption",
    "begin_mutation",
    "begin_orphaned_foreign_acquisition",
    "begin_recompute",
    "begin_recovery",
    "begin_save",
    "begin_saved_foreign_recovery_acquisition",
    "cancel_save_before_mutation",
    "claim_locked_error_handoff",
    "commit_save_as",
    "complete_acquisition",
    "complete_cancellation",
    "complete_dirty_adoption",
    "complete_local_save_and_clear",
    "complete_operation",
    "confirmed_takeover_foreign_recovery",
    "fail_acquisition_after_mutation",
    "get",
    "get_effective",
    "get_foreign_recovery",
    "handle_document_closed",
    "has_unresolved_owner",
    "heartbeat",
    "import_adjacent_foreign_recovery",
    "list_effective_records",
    "list_foreign_recoveries",
    "list_records",
    "mark_expired_stale",
    "mark_save_verified",
    "mark_stale",
    "rebind_closed_recovery_document",
    "reconcile_stale",
    "record_acquisition_snapshot",
    "record_error",
    "recover_orphaned_foreign_acquisition",
    "recover_orphaned_local_mcp_acquisition",
    "refresh_local_recovery_document_identity",
    "refresh_orphaned_foreign_document_identity",
    "release_clean",
    "repair_registered_document_identity",
    "reserve_save_as",
    "takeover",
    "try_baseline_preserving_document_identity_refresh",
    "update_local_dirty",
    "update_metadata",
]
