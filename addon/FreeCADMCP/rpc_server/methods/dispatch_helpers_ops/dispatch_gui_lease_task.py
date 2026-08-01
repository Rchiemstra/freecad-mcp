from __future__ import annotations

# ruff: noqa: F403, F405
from ._support import *
from .dispatch_gui_lease_enforced import run_enforced_lease_service_task
from .dispatch_gui_lease_paths import run_legacy_lease_task, run_unenforced_lease_task


def run_lease_aware_gui_task(self, original_task, captured, inflight, context):
    if inflight is not None:
        inflight.token.checkpoint("gui_revalidation")
    if captured["lease_enforced"] and _rpc_mod().document_lease_service is not None:
        return run_enforced_lease_service_task(self, original_task, captured, inflight)

    if not captured["lease_enforced"]:
        return run_unenforced_lease_task(self, original_task, captured, inflight)

    return run_legacy_lease_task(self, original_task, captured, inflight)
