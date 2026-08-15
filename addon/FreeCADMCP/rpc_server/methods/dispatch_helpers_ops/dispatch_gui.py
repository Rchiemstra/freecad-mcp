from __future__ import annotations

from ..cad_methods_ops.cad_mutation import cad_mutation_inflight
from ..cad_methods_ops.mutation_readiness_wait import (
    asynchronous_transient_document_keys,
    await_transient_mutation_readiness,
)

# ruff: noqa: F403, F405
from ._support import *
from .dispatch_gui_callbacks import build_gui_on_complete, build_replay_on_complete
from .dispatch_gui_errors import handle_gui_dispatch_error
from .dispatch_gui_lease_task import run_lease_aware_gui_task

"""GUI-thread dispatch with lease revalidation."""


def _build_mutation_readiness_probe(collaborators, captured, inflight):
    """Build a GUI-owner probe that never waits or enters a nested event loop."""

    document_names = tuple(str(name) for name in captured["doc_names"] if name)
    if not document_names:
        return None

    def probe():
        if inflight is not None:
            inflight.token.checkpoint("gui_mutation_readiness_probe")
        documents = tuple(
            collaborators.freecad.getDocument(name) for name in document_names
        )
        # A closed document is a permanent preflight error handled by the
        # normal task.  It must not be stranded waiting for a native signal.
        if any(document is None for document in documents):
            return None
        readiness, _settled = await_transient_mutation_readiness(
            documents,
            inflight=inflight,
            # The dispatcher continuation owns only asynchronous native
            # states. Operation-specific code retains mustExecute policy.
            allow_pending_recompute=True,
        )
        waiting = asynchronous_transient_document_keys(
            readiness,
            allow_pending_recompute=True,
        )
        if not waiting:
            return None
        return GuiDeferDecision(
            document_keys=document_names,
            reason="native_mutation_readiness:" + ",".join(waiting),
        )

    return probe


def dispatch_gui(
    self,
    task,
    timeout=None,
    *,
    late_on_complete=None,
    late_result_transform=None,
    journal_late_completion=True,
):
    """Run *task* on the GUI thread and preserve legacy string errors.

    ``late_on_complete`` is invoked when the GUI task finishes, including
    after the waiter has already timed out (completion_uncertain).
    """
    collaborators = self._execution_collaborators
    dispatcher = collaborators.gui_dispatcher
    if dispatcher is None:
        return "RPC GUI dispatcher is not initialized"
    t = timeout if timeout is not None else self.TIMEOUT
    completion_seen = threading.Event()
    completion_lock = threading.RLock()
    completion_handoff = {"held": False}
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
                self,
                collaborators,
                original_task,
                captured,
                inflight,
                context,
                completion_lock=completion_lock,
                completion_handoff=completion_handoff,
            )

    replay_on_complete = None
    replay_cache = collaborators.request_replay_cache
    completion_runtime_id = collaborators.runtime_id
    if context and replay_cache is not None and journal_late_completion:
        replay_on_complete = build_replay_on_complete(
            context,
            replay_cache,
            completion_runtime_id,
            result_transform=late_result_transform,
        )

    session_id = inflight.session_id if inflight is not None else None
    gui_phase_registered = False
    if inflight is not None:
        collaborators.inflight_request_registry.begin_gui_phase(
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
        completion_lock=completion_lock,
        completion_handoff=completion_handoff,
        replay_on_complete=replay_on_complete,
        late_on_complete=late_on_complete,
        collaborators=collaborators,
    )

    readiness_probe = (
        _build_mutation_readiness_probe(collaborators, captured, inflight)
        if context
        and bool(
            getattr(dispatcher, "supports_readiness_continuations", False)
        )
        else None
    )

    try:
        def gui_task():
            # ``run_cad_mutation`` is invoked inside this callback.  A
            # ContextVar preserves the same request id/cancellation token for
            # its bounded readiness settle turn without widening CAD's
            # dependency container with dispatcher policy.
            with cad_mutation_inflight(inflight):
                return task()

        submit_options = {
            "request_id": request_id,
            "session_id": session_id,
            "on_complete": (
                on_complete
                if (
                    gui_phase_registered
                    or context is not None
                    or replay_on_complete
                    or late_on_complete is not None
                )
                else None
            ),
        }
        if readiness_probe is not None:
            submit_options.update(
                defer_probe=readiness_probe,
                document_keys=tuple(captured["doc_names"]),
            )
        return dispatcher.submit(gui_task, t, **submit_options)
    except GuiDispatchError as exc:
        return handle_gui_dispatch_error(
            self,
            exc,
            inflight=inflight,
            context=context,
            request_id=request_id,
            gui_phase_registered=gui_phase_registered,
            completion_seen=completion_seen,
            completion_lock=completion_lock,
            collaborators=collaborators,
        )


def dispatch_snapshot_gui(self, task):
    """Snapshot saveCopy has no safe hard timeout; wait outside Qt."""
    collaborators = self._execution_collaborators
    dispatcher = collaborators.gui_dispatcher
    if dispatcher is None:
        return "RPC GUI dispatcher is not initialized"
    try:
        return dispatcher.submit(task, None)
    except GuiDispatchError as exc:
        collaborators.logger.error("RPC snapshot dispatch failed: %s", exc)
        return str(exc)
