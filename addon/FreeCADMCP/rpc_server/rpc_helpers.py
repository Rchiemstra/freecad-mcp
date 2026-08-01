"""Module-level RPC helpers (re-exported from ``rpc_server`` shims)."""

from .rpc_helpers_ops._adoption_gui import (
    _authorize_locked_error_handoff_gui,
    _confirm_dirty_document_adoption_gui,
)
from .rpc_helpers_ops.diagnostics import (
    _format_identity_registration_error,
    _import_core_authority,
    _lease_service_error,
    _redact_rpc_diagnostic,
)
from .rpc_helpers_ops.document_identity import (
    _candidate_matches_selector_target,
    _credential_for_document,
    _credential_for_selector,
    _credential_from_wire,
    _effective_sidecar_block,
    _ensure_v2_document,
    _freecad_version_parts,
    _live_document_from_selector,
)
from .rpc_helpers_ops.feature_properties import _set_extrusion_symmetric, _set_feature_bool
from .rpc_helpers_ops.generated_execute import (
    _generated_execute_signature,
    _generated_operation_method_spec,
    _validate_generated_operation_envelope,
)
from .rpc_helpers_ops.reconcile import (
    _assert_never_saved_stale_continuity,
    _discard_terminal_snapshot,
    _recovery_snapshot_intact,
    _snapshot_mutation_context_for_request,
    _stale_reconcile_already_recovered,
    _stale_reconcile_classify,
    _stale_reconcile_never_saved_ready,
    _stale_reconcile_saved_baseline_ready,
    _v2_status_for_context,
)
from .rpc_helpers_ops.save_validation import (
    _SAVE_VALIDATION_MARKER,
    _saved_document_expectations,
    _validate_saved_document_worker,
)
from .rpc_helpers_ops.validation_evidence import (
    _assert_mutation_file_metadata_unchanged,
    _live_validation_evidence,
)

__all__ = [
    "_SAVE_VALIDATION_MARKER",
    "_assert_mutation_file_metadata_unchanged",
    "_assert_never_saved_stale_continuity",
    "_authorize_locked_error_handoff_gui",
    "_candidate_matches_selector_target",
    "_confirm_dirty_document_adoption_gui",
    "_credential_for_document",
    "_credential_for_selector",
    "_credential_from_wire",
    "_discard_terminal_snapshot",
    "_effective_sidecar_block",
    "_ensure_v2_document",
    "_format_identity_registration_error",
    "_freecad_version_parts",
    "_generated_execute_signature",
    "_generated_operation_method_spec",
    "_import_core_authority",
    "_lease_service_error",
    "_live_document_from_selector",
    "_live_validation_evidence",
    "_recovery_snapshot_intact",
    "_redact_rpc_diagnostic",
    "_saved_document_expectations",
    "_set_extrusion_symmetric",
    "_set_feature_bool",
    "_snapshot_mutation_context_for_request",
    "_stale_reconcile_already_recovered",
    "_stale_reconcile_classify",
    "_stale_reconcile_never_saved_ready",
    "_stale_reconcile_saved_baseline_ready",
    "_v2_status_for_context",
    "_validate_generated_operation_envelope",
    "_validate_saved_document_worker",
]


