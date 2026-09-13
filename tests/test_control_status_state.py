from types import SimpleNamespace

from addon.FreeCADMCP.rpc_server.methods.lifecycle_methods_ops.control_status_state import (
    inflight_state,
)


def test_active_uncertain_gui_request_remains_running_after_timeout():
    inflight = SimpleNamespace(
        terminal=True,
        cancellation_requested=False,
        uncertain=True,
        active_gui_phases=("mutation",),
        terminal_status="failed",
    )
    status = SimpleNamespace(status="completed", response=None)

    assert inflight_state(inflight, status) == "running_after_timeout"


def test_late_success_replaces_handler_timeout_as_completed_status():
    inflight = SimpleNamespace(
        terminal=True,
        cancellation_requested=False,
        uncertain=True,
        active_gui_phases=(),
        terminal_status="failed",
    )
    status = SimpleNamespace(
        status="completed", response={"late_completion": True, "ok": True}
    )

    assert inflight_state(inflight, status) == "completed"


def test_cancellation_precedes_uncertain_active_gui_status():
    inflight = SimpleNamespace(
        terminal=True,
        cancellation_requested=True,
        uncertain=True,
        active_gui_phases=("mutation",),
        terminal_status=None,
    )
    status = SimpleNamespace(status="in_progress", response=None)

    assert inflight_state(inflight, status) == "cancel_requested"
