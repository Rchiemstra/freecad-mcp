from __future__ import annotations

# ruff: noqa: F403
from ._support import *


def run_lease_aware_gui_task(
    self,
    collaborators,
    original_task,
    captured,
    inflight,
    context,
    *,
    completion_lock,
    completion_handoff,
):
    """Run the GUI task after transport cancellation revalidation.

    The operation adapter itself owns the call into FreeCAD's native
    compatibility-mutation boundary.  This dispatcher deliberately performs no
    lease authorization, sidecar comparison, mutation-owner scoping, or dirty
    state transition.
    """

    del self, collaborators, captured, context, completion_lock, completion_handoff
    if inflight is not None:
        inflight.token.checkpoint("gui_revalidation")
    return original_task()
