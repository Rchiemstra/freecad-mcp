"""Production-shaped Phase 16 GUI dispatch envelope regressions."""

from __future__ import annotations

import json
import threading
from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.dispatch.gui_errors import GuiDispatchTimeout
from addon.FreeCADMCP.rpc_server.methods.dispatch_helpers_ops import (
    dispatch_gui_callbacks,
    dispatch_gui_errors,
)
from addon.FreeCADMCP.rpc_server.methods.gui_methods_ops.collaboration_context_dispatch import (
    GuiDispatchFailure,
    _unwrap_callback_value,
    dispatch_gui,
)
from addon.FreeCADMCP.rpc_server.methods.dispatch_helpers_ops.dispatch_gui_callbacks import (
    build_gui_on_complete,
    build_replay_on_complete,
)
from addon.FreeCADMCP.rpc_server.methods.dispatch_helpers_ops.dispatch_gui_lease_enforced import (
    _complete_gui_lease_operations,
)

pytestmark = pytest.mark.unit


def _facade(dispatch):
    return SimpleNamespace(_gui_collaborators=SimpleNamespace(dispatch_gui=dispatch))


def test_production_mutation_health_envelope_unwraps_callback_value():
    facade = _facade(
        lambda _facade, callback, **_kwargs: {
            "success": True,
            "result": callback(),
            "transaction": {"enabled": True},
            "document_health": {"verdict": "healthy"},
        }
    )

    assert dispatch_gui(facade, lambda: {"ok": True}) == {"ok": True}


def test_production_mutation_health_envelope_reraises_callback_exception():
    failure = RuntimeError("callback failed")

    def production_dispatch(_facade, callback, **_kwargs):
        result = callback()
        assert result["success"] is False
        return {
            **result,
            "transaction": {"enabled": True, "abort_succeeded": True},
            "document_health": {"rollback_restored_health": True},
        }

    facade = _facade(production_dispatch)

    with pytest.raises(RuntimeError, match="callback failed") as caught:
        dispatch_gui(facade, lambda: (_ for _ in ()).throw(failure))

    assert caught.value is failure


def test_failed_health_envelope_wins_over_callback_exception():
    callback_failure = RuntimeError("callback failed")

    def failed_rollback(_facade, callback, **_kwargs):
        result = callback()
        return {
            **result,
            "success": False,
            "error_code": "TRANSACTION_ROLLBACK_FAILED",
            "error": "rollback failed",
        }

    facade = _facade(failed_rollback)

    with pytest.raises(GuiDispatchFailure) as caught:
        dispatch_gui(facade, lambda: (_ for _ in ()).throw(callback_failure))

    assert caught.value.error_code == "TRANSACTION_ROLLBACK_FAILED"
    assert caught.value.result["error"] == "rollback failed"


def test_late_success_callback_value_is_json_safe_for_replay_journal():
    journaled = []
    completed = []

    class ReplayCache:
        def journal_completion(self, runtime_id, request_id, response, **_kwargs):
            json.dumps(response, sort_keys=True)
            journaled.append((runtime_id, request_id, response))
            return True

    context = {
        "request_id": "request-1",
        "identity": {
            "authenticated_session_id": "session-1",
            "instance_id": "runtime-1",
        },
    }
    replay = build_replay_on_complete(
        context,
        ReplayCache(),
        "addon-runtime",
        result_transform=_unwrap_callback_value,
    )

    def production_dispatch(_facade, callback, **_kwargs):
        result = {
            **callback(),
            "transaction": {"enabled": True},
            "document_health": {"verdict": "healthy"},
        }
        completed.append(result)
        return result

    facade = _facade(production_dispatch)
    assert dispatch_gui(facade, lambda: {"ok": True}) == {"ok": True}
    production_result = completed[0]

    replay(
        "request-1",
        SimpleNamespace(ok=True, value=production_result, error=None),
    )

    assert journaled == [
        (
            "runtime-1",
            "request-1",
            {
                "ok": True,
                "request_id": "request-1",
                "addon_runtime_id": "addon-runtime",
                "late_completion": True,
                "result": {"ok": True},
            },
        )
    ]


def test_timed_out_completion_journals_before_handler_finished_race():
    replayed = []
    inflight = SimpleNamespace(session_id="session-1", request_id="request-1")
    terminal = SimpleNamespace(
        handler_finished=False,
        recovery_incident_id=None,
        cancellation_requested=False,
    )
    collaborators = SimpleNamespace(
        inflight_request_registry=SimpleNamespace(
            end_gui_phase=lambda *_args: terminal
        ),
        logger=SimpleNamespace(debug=lambda *_args, **_kwargs: None),
    )
    callback = build_gui_on_complete(
        SimpleNamespace(_complete_request_cancellation=lambda *_args, **_kwargs: None),
        inflight=inflight,
        context={},
        completion_seen=threading.Event(),
        completion_lock=threading.Lock(),
        completion_handoff={"held": False},
        replay_on_complete=lambda *args: replayed.append(args),
        late_on_complete=None,
        collaborators=collaborators,
    )
    outcome = SimpleNamespace(ok=True, value={"ok": True}, error=None, late=True)

    callback("request-1", outcome)

    assert replayed == [("request-1", outcome, terminal)]


def _timeout_race_harness():
    calls = []

    class Token:
        recovery_incident_id = None

        def mark_uncertain(self, _stage):
            calls.append("uncertain")
            self.recovery_incident_id = "incident-1"
            return self.snapshot()

        def mark_recovered(self, _stage):
            calls.append("recovered")
            self.recovery_incident_id = None
            return self.snapshot()

        def snapshot(self):
            return SimpleNamespace(
                mutation_started=True,
                recovery_incident_id=self.recovery_incident_id,
                cancellation_requested=False,
                handler_finished=False,
            )

    token = Token()
    inflight = SimpleNamespace(
        session_id="session-1", request_id="request-1", token=token
    )
    registry = SimpleNamespace(
        end_gui_phase=lambda *_args: token.snapshot(),
        refresh_terminal=lambda *_args: token.snapshot(),
    )
    collaborators = SimpleNamespace(
        inflight_request_registry=registry,
        document_lease_service=SimpleNamespace(
            record_error=lambda *_args, **_kwargs: calls.append("lease-error")
        ),
        credential_for_document=lambda *_args: (object(), object()),
        redact_rpc_diagnostic=lambda *_args, **_kwargs: "redacted",
        logger=SimpleNamespace(
            error=lambda *_args, **_kwargs: None,
            debug=lambda *_args, **_kwargs: None,
        ),
    )
    error = GuiDispatchTimeout(
        "late",
        request_id="request-1",
        execution_started=True,
        completion_uncertain=True,
    )
    error.error_code = "GUI_TIMEOUT_DURING_EXECUTION"
    context = {
        "doc_names": ("Model",),
        "identity": {},
        "request_id": "request-1",
    }
    return calls, inflight, collaborators, error, context


def test_completion_first_skips_false_uncertainty_and_lease_error(monkeypatch):
    monkeypatch.setattr(dispatch_gui_errors, "emit_telemetry", lambda *_a, **_k: None)
    calls, inflight, collaborators, error, context = _timeout_race_harness()
    completion_seen = threading.Event()
    completion_seen.set()

    dispatch_gui_errors.handle_gui_dispatch_error(
        SimpleNamespace(),
        error,
        inflight=inflight,
        context=context,
        request_id="request-1",
        gui_phase_registered=True,
        completion_seen=completion_seen,
        completion_lock=threading.Lock(),
        collaborators=collaborators,
    )

    assert "uncertain" not in calls
    assert "lease-error" not in calls


def test_timeout_first_is_recovered_by_late_completion(monkeypatch):
    monkeypatch.setattr(dispatch_gui_errors, "emit_telemetry", lambda *_a, **_k: None)
    monkeypatch.setattr(
        dispatch_gui_callbacks, "emit_telemetry", lambda *_a, **_k: None
    )
    calls, inflight, collaborators, error, context = _timeout_race_harness()
    completion_seen = threading.Event()
    completion_lock = threading.Lock()

    dispatch_gui_errors.handle_gui_dispatch_error(
        SimpleNamespace(),
        error,
        inflight=inflight,
        context=context,
        request_id="request-1",
        gui_phase_registered=True,
        completion_seen=completion_seen,
        completion_lock=completion_lock,
        collaborators=collaborators,
    )
    callback = dispatch_gui_callbacks.build_gui_on_complete(
        SimpleNamespace(_complete_request_cancellation=lambda *_a, **_k: None),
        inflight=inflight,
        context=context,
        completion_seen=completion_seen,
        completion_lock=completion_lock,
        completion_handoff={"held": False},
        replay_on_complete=None,
        late_on_complete=None,
        collaborators=collaborators,
    )
    callback(
        "request-1",
        SimpleNamespace(ok=True, value={"ok": True}, error=None, late=True),
    )

    assert calls == ["uncertain", "lease-error", "recovered"]


def test_terminal_gui_success_recovers_exact_matching_uncertainty_lease():
    calls = []

    class Service:
        def complete_operation(self, credential, *, dirty):
            calls.append(("complete", credential, dirty))
            if len([call for call in calls if call[0] == "complete"]) == 1:
                raise RuntimeError("lease became uncertain")

        def authorize(self, credential):
            calls.append(("authorize", credential))
            return SimpleNamespace(
                state=SimpleNamespace(value="LOCKED_ERROR"),
                error=SimpleNamespace(
                    code="GUI_COMPLETION_UNCERTAIN", request_id="request-1"
                ),
            )

        def begin_recovery(self, credential, *, operation):
            calls.append(("recover", credential, operation))

    collaborators = SimpleNamespace(
        freecad=SimpleNamespace(
            getDocument=lambda _name: SimpleNamespace(Modified=True)
        ),
        document_lease_service=Service(),
        redact_rpc_diagnostic=lambda value, **_kwargs: str(value),
    )
    inflight = SimpleNamespace(
        token=SimpleNamespace(
            snapshot=lambda: SimpleNamespace(recovery_incident_id="incident-1")
        )
    )

    _complete_gui_lease_operations(
        collaborators,
        {"request_id": "request-1", "identity": {}},
        inflight,
        [("Model", "credential", None)],
        "animate_placement",
        {"ok": True},
        False,
    )

    assert calls == [
        ("complete", "credential", True),
        ("authorize", "credential"),
        ("recover", "credential", "animate_placement:late_completion"),
        ("complete", "credential", True),
    ]
