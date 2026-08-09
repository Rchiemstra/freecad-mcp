"""Declarative shim — generated connection method lives in generated/capabilities."""

from freecad_mcp.generated.capabilities.connection_methods import (
    connection_acquisition_helpers as _generated,
)

is_permanent_auth_failure = _generated.is_permanent_auth_failure
handoff_claimable = _generated.handoff_claimable
try_claim_handoff_result = _generated.try_claim_handoff_result
handoff_terminal_result = _generated.handoff_terminal_result
handoff_still_pending = _generated.handoff_still_pending
handoff_terminal_state = _generated.handoff_terminal_state
disconnected_handoff_result = _generated.disconnected_handoff_result
auth_failure_handoff_result = _generated.auth_failure_handoff_result
pending_handoff_result = _generated.pending_handoff_result
poll_locked_error_handoff = _generated.poll_locked_error_handoff
process_handoff_status_poll = _generated.process_handoff_status_poll
_legacy_authority_removed = _generated._legacy_authority_removed

__all__ = [  # noqa: RUF022
    'is_permanent_auth_failure',
    'handoff_claimable',
    'try_claim_handoff_result',
    'handoff_terminal_result',
    'handoff_still_pending',
    'handoff_terminal_state',
    'disconnected_handoff_result',
    'auth_failure_handoff_result',
    'pending_handoff_result',
    'poll_locked_error_handoff',
    'process_handoff_status_poll',
    '_legacy_authority_removed',
]
