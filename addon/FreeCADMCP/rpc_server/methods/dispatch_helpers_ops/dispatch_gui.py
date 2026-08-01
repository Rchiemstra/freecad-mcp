from __future__ import annotations

# ruff: noqa: F403, F405
from ._support import *
from .dispatch_gui_callbacks import build_gui_on_complete, build_replay_on_complete
from .dispatch_gui_errors import handle_gui_dispatch_error
from .dispatch_gui_lease_task import run_lease_aware_gui_task

"""GUI-thread dispatch with lease revalidation."""


def dispatch_gui(self, task, timeout=None, *, late_on_complete=None):
    """Run *task* on the GUI thread and preserve legacy string errors.

    ``late_on_complete`` is invoked when the GUI task finishes, including
    after the waiter has already timed out (completion_uncertain).
    """
    dispatcher = _rpc_mod().gui_dispatcher
    if dispatcher is None:
        return "RPC GUI dispatcher is not initialized"
    t = timeout if timeout is not None else self.TIMEOUT
    context = getattr(self._mutation_context, "value", None)
    inflight = self._current_inflight()
    request_id = inflight.request_id if inflight is not None else None
    if context:
        captured = {
            "request_id": context["request_id"],
            "method": context["method"],
            "doc_keys": tuple(context["doc_keys"]),
            "doc_names": tuple(context["doc_names"]),
            "identity": dict(context["identity"]),
            "method_spec": context["method_spec"],
            "expected_objects": tuple(context.get("expected_objects", ())),
            "lease_enforced": bool(context.get("lease_enforced", True)),
        }
        request_id = captured["request_id"]
        original_task = task

        def task():
            return run_lease_aware_gui_task(
                self, original_task, captured, inflight, context
            )

    replay_on_complete = None
    replay_cache = _rpc_mod().rpc_request_replay_cache
    completion_runtime_id = _rpc_mod().rpc_server_runtime_id
    if context and replay_cache is not None:
        replay_on_complete = build_replay_on_complete(
            context, replay_cache, completion_runtime_id
        )

    completion_seen = threading.Event()
    session_id = inflight.session_id if inflight is not None else None
    gui_phase_registered = False
    if inflight is not None:
        _rpc_mod().rpc_inflight_request_registry.begin_gui_phase(
            inflight.session_id,
            inflight.request_id,
            f"gui:{context['method'] if context else 'lifecycle'}",
        )
        gui_phase_registered = True

    on_complete = build_gui_on_complete(
        self,
        inflight=inflight,
        context=context,
        completion_seen=completion_seen,
        replay_on_complete=replay_on_complete,
        late_on_complete=late_on_complete,
    )

    try:
        return dispatcher.submit(
            task,
            t,
            request_id=request_id,
            session_id=session_id,
            on_complete=(
                on_complete
                if (
                    gui_phase_registered
                    or replay_on_complete
                    or late_on_complete is not None
                )
                else None
            ),
        )
    except GuiDispatchError as exc:
        return handle_gui_dispatch_error(
            self,
            exc,
            inflight=inflight,
            context=context,
            request_id=request_id,
            gui_phase_registered=gui_phase_registered,
            completion_seen=completion_seen,
        )


def dispatch_snapshot_gui(self, task):
    """Snapshot saveCopy has no safe hard timeout; wait outside Qt."""
    dispatcher = _rpc_mod().gui_dispatcher
    if dispatcher is None:
        return "RPC GUI dispatcher is not initialized"
    try:
        return dispatcher.submit(task, None)
    except GuiDispatchError as exc:
        _rpc_mod().logger.error("RPC snapshot dispatch failed: %s", exc)
        return str(exc)
