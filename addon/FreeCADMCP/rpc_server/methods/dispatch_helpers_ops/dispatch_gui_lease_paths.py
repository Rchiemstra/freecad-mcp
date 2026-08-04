from __future__ import annotations

# ruff: noqa: F403, F405
from ._support import *

"""Unenforced and legacy GUI lease task paths."""


def run_unenforced_lease_task(self, collaborators, original_task, captured, inflight):
    documents = [
        collaborators.freecad.getDocument(name) for name in captured["doc_names"]
    ]
    if any(document is None for document in documents):
        return {
            "success": False,
            "error_code": "DOCUMENT_NOT_FOUND",
            "error": "A declared document closed before mutation execution",
        }
    if inflight is not None:
        inflight.token.begin_mutation("gui_mutation_scope_resolved")
    result, _failed = self._execute_mutation_with_health(
        original_task,
        documents,
        captured["method_spec"],
        expected_objects=captured["expected_objects"],
        inflight=inflight,
        request_id=captured["request_id"],
    )
    return result


def _transition_legacy_leases(
    collaborators, dl, captured, token, operation, *, failed=False, result=None
):
    dirty_by_name = {}
    for name in captured["doc_names"]:
        doc = collaborators.freecad.getDocument(name)
        dirty_by_name[name] = document_modified_or_dirty(doc) if doc is not None else True
    for index, key in enumerate(captured["doc_keys"]):
        name = captured["doc_names"][index] if index < len(captured["doc_names"]) else None
        dl.transition_lease(
            key,
            token,
            (
                dl.LeaseState.LOCKED_ERROR.value
                if failed
                else dl.LeaseState.LOCKED_IDLE.value
            ),
            current_operation=(f"error:{operation}" if failed else ""),
            document_dirty=dirty_by_name.get(name),
            request_id=captured["request_id"],
            error=(
                {
                    "code": "operation_failed",
                    "message": str(
                        result.get("error") or result.get("message") or operation
                    ),
                }
                if failed and isinstance(result, dict)
                else None
            ),
        )


def run_legacy_lease_task(self, collaborators, original_task, captured, inflight):
    dl = collaborators.import_document_lock()
    for key in captured["doc_keys"]:
        allowed = dl.check_mutation_allowed(key, identity=captured["identity"])
        if not allowed.get("success"):
            return allowed

    marker_keys = tuple(sorted(set(list(captured["doc_keys"]) + list(captured["doc_names"]))))
    token = captured["identity"].get("lease_token") or ""
    operation = captured["method"]
    if inflight is not None:
        inflight.token.begin_mutation("gui_mutation_authorized")
    started_state = (
        dl.LeaseState.LOCKED_RECOMPUTING.value
        if "recompute" in operation
        else dl.LeaseState.LOCKED_EDITING.value
    )
    for key in captured["doc_keys"]:
        transition = dl.transition_lease(
            key,
            token,
            started_state,
            current_operation=operation,
            request_id=captured["request_id"],
        )
        if not transition.get("success"):
            return transition
    dl.begin_agent_mutation_scope(captured["request_id"], marker_keys)
    try:
        if inflight is not None:
            inflight.token.checkpoint("gui_mutation_invocation")
        result = original_task()
        failed = isinstance(result, dict) and (
            result.get("success") is False or result.get("ok") is False
        )
        _transition_legacy_leases(
            collaborators,
            dl,
            captured,
            token,
            operation,
            failed=failed,
            result=result,
        )
        return result
    except Exception as exc:
        for key in captured["doc_keys"]:
            dl.transition_lease(
                key,
                token,
                dl.LeaseState.LOCKED_ERROR.value,
                current_operation=f"error:{operation}",
                request_id=captured["request_id"],
                error={
                    "code": type(exc).__name__,
                    "message": str(exc),
                },
            )
        raise
    finally:
        dl.end_agent_mutation_scope(captured["request_id"], marker_keys)
