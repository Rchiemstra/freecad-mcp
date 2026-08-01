from __future__ import annotations

# ruff: noqa: F403, F405
from ._support import *

"""GUI dispatch callback builders."""


def build_replay_on_complete(context, replay_cache, completion_runtime_id):
    session_id = context["identity"].get("authenticated_session_id")
    replay_runtime_id = context["identity"].get("instance_id")
    addon_request_id = context.get("request_id")
    replay_secrets = tuple(
        str(value)
        for value in (
            context["identity"].get("rpc_session_token"),
            *(
                item.get("token")
                for item in context["identity"].get("lease_credentials", ())
                if isinstance(item, dict)
            ),
        )
        if value
    )
    if not (session_id and replay_runtime_id and addon_request_id):
        return None

    def replay_on_complete(completed_request_id, outcome, cancellation=None):
        result = outcome.value if outcome.ok else None
        result_failed = isinstance(result, dict) and (
            result.get("success") is False or result.get("ok") is False
        )
        response = {
            "ok": bool(
                outcome.ok
                and not result_failed
                and not (cancellation and cancellation.cancellation_requested)
            ),
            "request_id": completed_request_id,
            "addon_runtime_id": completion_runtime_id,
            "late_completion": True,
        }
        if cancellation and cancellation.cancellation_requested:
            response["error"] = {
                "code": (
                    "REQUEST_CANCELLED_AFTER_MUTATION"
                    if cancellation.mutation_started or cancellation.uncertain
                    else "REQUEST_CANCELLED"
                ),
                "message": "Authenticated request was cancelled",
            }
            response["cancellation"] = cancellation.to_public_dict()
        elif outcome.ok:
            response["result"] = result
        else:
            response["error"] = {
                "code": "GUI_TASK_FAILED",
                "message": outcome.error or "GUI task failed",
            }
        replay_cache.journal_completion(
            replay_runtime_id,
            completed_request_id,
            response,
            secrets=replay_secrets,
        )

    return replay_on_complete


def build_gui_on_complete(
    self,
    *,
    inflight,
    context,
    completion_seen,
    replay_on_complete,
    late_on_complete,
):
    def on_complete(completed_request_id, outcome):
        completion_seen.set()
        completion_state = None
        if inflight is not None:
            completion_state = _rpc_mod().rpc_inflight_request_registry.end_gui_phase(
                inflight.session_id, inflight.request_id
            )
            if completion_state is not None and completion_state.recovery_incident_id:
                completion_state = inflight.token.mark_recovered("recovery_completed")
                emit_telemetry(
                    "recovery",
                    ("recovery_completed" if outcome.ok else "recovery_failed"),
                    status="succeeded" if outcome.ok else "failed",
                    error_code=None if outcome.ok else "GUI_TASK_FAILED",
                    request_id=inflight.request_id,
                    execution_id=inflight.request_id,
                    recovery_incident_id=(completion_state.recovery_incident_id),
                    payload={"late_completion_available": True},
                )
            if completion_state is not None and completion_state.cancellation_requested:
                self._complete_request_cancellation(
                    inflight,
                    dirty=(True if completion_state.mutation_started else None),
                )
                completion_state = _rpc_mod().rpc_inflight_request_registry.refresh_terminal(
                    inflight.session_id, inflight.request_id
                )
        if replay_on_complete is not None and (
            completion_state is None or completion_state.handler_finished
        ):
            replay_on_complete(completed_request_id, outcome, completion_state)
        if late_on_complete is not None:
            try:
                late_on_complete(completed_request_id, outcome)
            except Exception:
                _rpc_mod().logger.debug("late_on_complete callback failed", exc_info=True)

    return on_complete
