from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType as _MappingProxyType

from .lease_state import LeaseState

TERMINAL_STATES = frozenset(
    {LeaseState.UNLOCKED_SAVED, LeaseState.UNLOCKED_DIRTY}
)


# Frozen schema-v2 transition metadata retained for historic interpretation.
# No function in this module validates or performs a transition.
ALLOWED_TRANSITIONS: Mapping[LeaseState, frozenset[LeaseState]] = _MappingProxyType({
    LeaseState.ACQUIRING: frozenset(
        {LeaseState.LOCKED_IDLE, LeaseState.LOCKED_ERROR, LeaseState.STALE}
    ),
    LeaseState.LOCKED_IDLE: frozenset(
        {
            LeaseState.LOCKED_EDITING,
            LeaseState.LOCKED_RECOMPUTING,
            LeaseState.LOCKED_SAVING,
            LeaseState.LOCKED_ERROR,
            LeaseState.USER_INTERVENED,
            LeaseState.CANCELLING,
            LeaseState.RELEASING,
            LeaseState.STALE,
        }
    ),
    LeaseState.LOCKED_EDITING: frozenset(
        {
            LeaseState.LOCKED_IDLE,
            LeaseState.LOCKED_RECOMPUTING,
            LeaseState.LOCKED_ERROR,
            LeaseState.USER_INTERVENED,
            LeaseState.CANCELLING,
            LeaseState.STALE,
        }
    ),
    LeaseState.LOCKED_RECOMPUTING: frozenset(
        {
            LeaseState.LOCKED_IDLE,
            LeaseState.LOCKED_ERROR,
            LeaseState.USER_INTERVENED,
            LeaseState.CANCELLING,
            LeaseState.STALE,
        }
    ),
    LeaseState.LOCKED_SAVING: frozenset(
        {
            LeaseState.LOCKED_IDLE,
            LeaseState.LOCKED_ERROR,
            LeaseState.USER_INTERVENED,
            LeaseState.CANCELLING,
            LeaseState.STALE,
        }
    ),
    LeaseState.LOCKED_ERROR: frozenset(
        {
            LeaseState.LOCKED_EDITING,
            LeaseState.LOCKED_SAVING,
            LeaseState.USER_INTERVENED,
            LeaseState.CANCELLING,
            LeaseState.UNLOCKED_DIRTY,
            LeaseState.STALE,
        }
    ),
    LeaseState.USER_INTERVENED: frozenset(
        {
            LeaseState.RELEASING,
            LeaseState.UNLOCKED_SAVED,
            LeaseState.UNLOCKED_DIRTY,
            LeaseState.STALE,
        }
    ),
    LeaseState.CANCELLING: frozenset(
        {
            LeaseState.LOCKED_IDLE,
            LeaseState.LOCKED_ERROR,
            LeaseState.USER_INTERVENED,
            LeaseState.STALE,
        }
    ),
    LeaseState.RELEASING: frozenset(
        {LeaseState.UNLOCKED_SAVED, LeaseState.LOCKED_ERROR, LeaseState.STALE}
    ),
    LeaseState.UNLOCKED_SAVED: frozenset({LeaseState.ACQUIRING}),
    LeaseState.UNLOCKED_DIRTY: frozenset(
        {
            LeaseState.RELEASING,
            LeaseState.UNLOCKED_SAVED,
            LeaseState.ACQUIRING,
        }
    ),
    LeaseState.STALE: frozenset(
        {
            LeaseState.LOCKED_IDLE,
            LeaseState.USER_INTERVENED,
            LeaseState.UNLOCKED_SAVED,
            LeaseState.UNLOCKED_DIRTY,
        }
    ),
})
