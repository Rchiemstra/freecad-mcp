from __future__ import annotations

# ruff: noqa: F403, F405
from ._support import *

"""GUI dispatch error handling."""


def handle_gui_dispatch_error(
    self,
    exc,
    *,
    inflight,
    context,
    request_id,
    gui_phase_registered,
    completion_seen,
):
    if (
        gui_phase_registered
        and not completion_seen.is_set()
        and not (isinstance(exc, GuiDispatchTimeout) and exc.execution_started)
    ):
        _rpc_mod().rpc_inflight_request_registry.end_gui_phase(
            inflight.session_id, inflight.request_id
        )
    _rpc_mod().logger.error("RPC GUI dispatch failed: %s", exc)
    recovery = None
    if isinstance(exc, GuiDispatchTimeout) and exc.completion_uncertain and inflight is not None:
        recovery = inflight.token.mark_uncertain("gui_completion_uncertain")
        emit_telemetry(
            "recovery",
            "recovery_started",
            status="warning",
            error_code="GUI_COMPLETION_UNCERTAIN",
            request_id=inflight.request_id,
            execution_id=inflight.request_id,
            recovery_incident_id=recovery.recovery_incident_id,
            payload={
                "stage": "gui_execution",
                "mutation_started": recovery.mutation_started,
            },
        )
    if (
        context
        and _rpc_mod().document_lease_service is not None
        and isinstance(exc, GuiDispatchTimeout)
        and exc.completion_uncertain
    ):
        for name in context["doc_names"]:
            try:
                credential, _document_identity = _rpc_mod()._credential_for_document(
                    name, context["identity"]
                )
                _rpc_mod().document_lease_service.record_error(
                    credential,
                    code="GUI_COMPLETION_UNCERTAIN",
                    message=_rpc_mod()._redact_rpc_diagnostic(
                        exc, identity=context["identity"], inflight=inflight
                    ),
                    request_id=context["request_id"],
                    dirty=True,
                )
            except Exception:
                pass
    code = getattr(exc, "error_code", "GUI_DISPATCH_FAILED")
    timeout_snapshot = inflight.token.snapshot() if inflight is not None else None
    return {
        "success": False,
        "error_code": code,
        "error": str(exc),
        "request_id": request_id,
        "timeout_stage": getattr(exc, "timeout_stage", None),
        "execution_started": bool(getattr(exc, "execution_started", False)),
        "mutation_started": bool(
            inflight is not None and inflight.token.snapshot().mutation_started
        ),
        "completion_uncertain": bool(getattr(exc, "completion_uncertain", False)),
        "recovery_incident_id": (
            timeout_snapshot.recovery_incident_id if timeout_snapshot is not None else None
        ),
    }
