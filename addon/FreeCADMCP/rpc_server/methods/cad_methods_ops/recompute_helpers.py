"""CAD RPC helpers extracted from ``FreeCADRPC`` (Phase 4 slice 4F)."""

from typing import Any

try:
    from part3_collaboration.admission import (
        actor_from_session,
        replay_or_protocol_error,
    )
    from part3_collaboration.history_head import (
        capture_redo_head,
        capture_undo_head,
        redo_head_matches,
        undo_head_matches,
    )
    from part3_collaboration.identity import (
        bootstrap_identity_selector,
        resolve_identity_bound_document,
    )
    from part3_collaboration.operation_terminal_store import (
        check_operation_terminal,
        store_operation_terminal,
    )
except ImportError:  # pragma: no cover - package test layout
    from addon.FreeCADMCP.part3_collaboration.admission import (
        actor_from_session,
        replay_or_protocol_error,
    )
    from addon.FreeCADMCP.part3_collaboration.history_head import (
        capture_redo_head,
        capture_undo_head,
        redo_head_matches,
        undo_head_matches,
    )
    from addon.FreeCADMCP.part3_collaboration.identity import (
        bootstrap_identity_selector,
        resolve_identity_bound_document,
    )
    from addon.FreeCADMCP.part3_collaboration.operation_terminal_store import (
        check_operation_terminal,
        store_operation_terminal,
    )

from .cad_mutation import (
    admit_cad_mutation,
    current_cad_mutation_inflight,
    postflight_cad_mutation,
)


def _error(code: str, message: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "success": False,
        "ok": False,
        "error_code": code,
        "error": message,
    }
    payload.update(extra)
    return payload


def _selector_dict(selector: Any) -> dict[str, Any] | None:
    if isinstance(selector, dict):
        return selector
    return None


def _store_history_terminal(
    actor_id: str,
    operation_id: str,
    canonical_payload: dict[str, Any],
    document: Any,
    terminal_result: dict[str, Any],
) -> None:
    selector = bootstrap_identity_selector(document)
    store_operation_terminal(
        actor_id,
        str(operation_id),
        canonical_payload,
        document_instance_id=int(selector.document_instance_id),
        lifecycle_epoch=int(selector.lifecycle_epoch),
        terminal_result=terminal_result,
    )


def _history_replay_result(
    actor_id: str,
    operation_id: str,
    canonical_payload: dict[str, Any],
    document: Any,
) -> dict[str, Any] | None:
    if not operation_id:
        return _error("OPERATION_ID_REQUIRED", "operation_id is required")
    selector = bootstrap_identity_selector(document)
    replay = check_operation_terminal(
        actor_id,
        operation_id,
        canonical_payload,
        live_document_instance_id=int(selector.document_instance_id),
        live_lifecycle_epoch=int(selector.lifecycle_epoch),
    )
    return replay_or_protocol_error(replay)


def _finish_history_mutation(
    document: Any,
    *,
    actor_id: str,
    operation_id: str,
    canonical_payload: dict[str, Any],
) -> Any:
    """Target recompute after undo/redo, then postflight (ADR §11.1 target policy)."""

    document.recompute()
    result = postflight_cad_mutation(document, True)
    if isinstance(result, dict) and (
        result.get("success") is False or result.get("ok") is False
    ):
        # History action already applied; do not store a failure terminal (ADR §2.2).
        failure = dict(result)
        failure["operation_id"] = operation_id
        return failure

    terminal: dict[str, Any] = {"success": True, "operation_id": operation_id}
    if isinstance(result, dict):
        terminal.update(result)
        terminal.setdefault("success", True)
    _store_history_terminal(actor_id, operation_id, canonical_payload, document, terminal)
    return terminal


def collect_invalid_objects(freecad) -> dict[str, list[dict[str, Any]]]:
    flagged: dict[str, list[dict[str, Any]]] = {}
    for doc_name, doc in freecad.listDocuments().items():
        entries = []
        for obj in doc.Objects:
            try:
                state = list(getattr(obj, "State", []))
                if any(s in ("Invalid", "Error", "Touched") for s in state):
                    entries.append(
                        {
                            "name": obj.Name,
                            "label": getattr(obj, "Label", obj.Name),
                            "state": state,
                        }
                    )
            except Exception:
                pass
        if entries:
            flagged[doc_name] = entries
    return flagged


def classify_recompute_errors(
    before: dict[str, list[dict[str, Any]]],
    after: dict[str, list[dict[str, Any]]],
    target_doc: str | None,
) -> dict[str, list[dict[str, Any]]]:
    def _key(doc: str, name: str) -> tuple[str, str]:
        return doc, name

    before_keys = {
        _key(doc, item["name"]) for doc, items in before.items() for item in items
    }
    target_errors: list[dict[str, Any]] = []
    pre_existing: list[dict[str, Any]] = []
    unrelated: list[dict[str, Any]] = []
    for doc, items in after.items():
        for item in items:
            entry = {
                "document": doc,
                "object": item["name"],
                "state": item["state"],
            }
            key = _key(doc, item["name"])
            if target_doc and doc == target_doc:
                if key in before_keys:
                    pre_existing.append(entry)
                else:
                    target_errors.append(entry)
            else:
                unrelated.append(entry)
    return {
        "target_recompute_errors": target_errors,
        "pre_existing_target_errors": pre_existing,
        "unrelated_document_errors": unrelated,
    }


def get_recompute_log(self, doc_name: str) -> list:
    """Return recompute state for every object in a document (read-only)."""
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: get_recompute_log_gui(doc_name, freecad=collaborators.freecad)
    )
    return res if isinstance(res, list) else [{"error": res}]


def get_recompute_log_gui(doc_name: str, *, freecad) -> list:
    doc = freecad.getDocument(doc_name)
    if not doc:
        return [{"error": f"Document '{doc_name}' not found"}]
    results = []
    for obj in doc.Objects:
        try:
            st = list(getattr(obj, "State", []))
            exprs = []
            for item in getattr(obj, "ExpressionEngine", None) or []:
                try:
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        exprs.append({"prop": str(item[0]), "expression": str(item[1])})
                    else:
                        exprs.append({"raw": str(item)})
                except Exception as ee:
                    exprs.append({"error": str(ee)})
            entry = {
                "name": obj.Name,
                "label": getattr(obj, "Label", obj.Name),
                "type_id": getattr(obj, "TypeId", ""),
                "state": st,
                "valid": not any(s in ("Invalid", "Error") for s in st),
                "expression_count": len(exprs),
            }
            if exprs:
                entry["expressions"] = exprs
            if any(s in ("Invalid", "Error") for s in st) and exprs:
                entry["expression_hint"] = (
                    "object invalid with bound expressions; check diagnose_parametric"
                )
            results.append(entry)
        except Exception as e:
            results.append({"name": getattr(obj, "Name", "?"), "error": str(e)})
    return results


def recompute_document(self, doc_name: str) -> dict:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: recompute_document_gui(doc_name, freecad=collaborators.freecad)
    )
    return self._adapt_gui_mutation_result(res)


def recompute_document_gui(doc_name, *, freecad):
    try:
        doc = freecad.getDocument(doc_name)
        if not doc:
            return f"Document '{doc_name}' not found."
        admission_failure = admit_cad_mutation(
            doc,
            inflight=current_cad_mutation_inflight(),
            allow_pending_recompute=True,
        )
        if admission_failure is not None:
            return admission_failure
        doc.recompute()
        return postflight_cad_mutation(doc, True)
    except Exception as e:
        return str(e)


def undo(
    self,
    doc_selector,
    operation_id,
    expected_undo_count=None,
    expected_undo_head=None,
) -> dict:
    actor_id, auth_failure = actor_from_session(self)
    if auth_failure is not None:
        return self._adapt_gui_mutation_result(auth_failure)
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: undo_gui(
            doc_selector,
            operation_id=str(operation_id),
            expected_undo_count=expected_undo_count,
            expected_undo_head=expected_undo_head,
            actor_id=actor_id,
            freecad=collaborators.freecad,
            rpc=self,
        )
    )
    return self._adapt_gui_mutation_result(res)


def undo_gui(
    doc_selector,
    *,
    operation_id: str,
    expected_undo_count,
    expected_undo_head,
    actor_id: str | None = None,
    freecad,
    rpc,
) -> Any:
    try:
        document, failure = resolve_identity_bound_document(
            freecad,
            _selector_dict(doc_selector),
        )
        if failure is not None:
            return failure

        canonical_payload = {
            "method": "undo",
            "doc_selector": dict(_selector_dict(doc_selector) or {}),
            "expected_undo_count": expected_undo_count,
            "expected_undo_head": expected_undo_head,
        }
        if actor_id is None:
            actor_id, auth_failure = actor_from_session(rpc)
            if auth_failure is not None:
                return auth_failure
        replay_result = _history_replay_result(
            actor_id, operation_id, canonical_payload, document
        )
        if replay_result is not None:
            return replay_result

        if expected_undo_count is None or expected_undo_head is None:
            failure = _error(
                "HISTORY_HEAD_REQUIRED",
                "expected_undo_count and expected_undo_head are required",
            )
            _store_history_terminal(actor_id, operation_id, canonical_payload, document, failure)
            return failure

        if not undo_head_matches(document, expected_undo_count, expected_undo_head):
            live = capture_undo_head(document)
            failure = _error(
                "HISTORY_HEAD_REJECTED",
                "document undo history head does not match the client expectation",
                expected_undo_count=int(expected_undo_count),
                expected_undo_head=str(expected_undo_head),
                current_undo_count=live["undo_count"],
                current_undo_head=live["undo_head"],
            )
            _store_history_terminal(actor_id, operation_id, canonical_payload, document, failure)
            return failure

        admission_failure = admit_cad_mutation(
            document, inflight=current_cad_mutation_inflight()
        )
        if admission_failure is not None:
            _store_history_terminal(
                actor_id, operation_id, canonical_payload, document, admission_failure
            )
            return admission_failure

        document.undo()
        return _finish_history_mutation(
            document,
            actor_id=actor_id,
            operation_id=operation_id,
            canonical_payload=canonical_payload,
        )
    except Exception as e:
        return str(e)


def redo(
    self,
    doc_selector,
    operation_id,
    expected_redo_count=None,
    expected_redo_head=None,
) -> dict:
    actor_id, auth_failure = actor_from_session(self)
    if auth_failure is not None:
        return self._adapt_gui_mutation_result(auth_failure)
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: redo_gui(
            doc_selector,
            operation_id=str(operation_id),
            expected_redo_count=expected_redo_count,
            expected_redo_head=expected_redo_head,
            actor_id=actor_id,
            freecad=collaborators.freecad,
            rpc=self,
        )
    )
    return self._adapt_gui_mutation_result(res)


def redo_gui(
    doc_selector,
    *,
    operation_id: str,
    expected_redo_count,
    expected_redo_head,
    actor_id: str | None = None,
    freecad,
    rpc,
) -> Any:
    try:
        document, failure = resolve_identity_bound_document(
            freecad,
            _selector_dict(doc_selector),
        )
        if failure is not None:
            return failure

        canonical_payload = {
            "method": "redo",
            "doc_selector": dict(_selector_dict(doc_selector) or {}),
            "expected_redo_count": expected_redo_count,
            "expected_redo_head": expected_redo_head,
        }
        if actor_id is None:
            actor_id, auth_failure = actor_from_session(rpc)
            if auth_failure is not None:
                return auth_failure
        replay_result = _history_replay_result(
            actor_id, operation_id, canonical_payload, document
        )
        if replay_result is not None:
            return replay_result

        if expected_redo_count is None or expected_redo_head is None:
            failure = _error(
                "HISTORY_HEAD_REQUIRED",
                "expected_redo_count and expected_redo_head are required",
            )
            _store_history_terminal(actor_id, operation_id, canonical_payload, document, failure)
            return failure

        if not redo_head_matches(document, expected_redo_count, expected_redo_head):
            live = capture_redo_head(document)
            failure = _error(
                "HISTORY_HEAD_REJECTED",
                "document redo history head does not match the client expectation",
                expected_redo_count=int(expected_redo_count),
                expected_redo_head=str(expected_redo_head),
                current_redo_count=live["redo_count"],
                current_redo_head=live["redo_head"],
            )
            _store_history_terminal(actor_id, operation_id, canonical_payload, document, failure)
            return failure

        admission_failure = admit_cad_mutation(
            document, inflight=current_cad_mutation_inflight()
        )
        if admission_failure is not None:
            _store_history_terminal(
                actor_id, operation_id, canonical_payload, document, admission_failure
            )
            return admission_failure

        document.redo()
        return _finish_history_mutation(
            document,
            actor_id=actor_id,
            operation_id=operation_id,
            canonical_payload=canonical_payload,
        )
    except Exception as e:
        return str(e)


def recompute_and_wait(self, doc_name: str) -> dict[str, Any]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: recompute_and_wait_gui(doc_name, collaborators=collaborators)
    )
    if isinstance(res, dict):
        return res
    return {"ok": False, "error": str(res)}


def recompute_and_wait_gui(doc_name: str, *, collaborators) -> Any:
    """Apply the standard mutation readiness gate before recompute/GUI drain."""

    document = collaborators.freecad.getDocument(doc_name)
    if document is None:
        return collaborators.recompute_and_wait(doc_name)
    admission_failure = admit_cad_mutation(
        document,
        inflight=current_cad_mutation_inflight(),
        allow_pending_recompute=True,
    )
    if admission_failure is not None:
        return admission_failure
    result = collaborators.recompute_and_wait(doc_name)
    return postflight_cad_mutation(document, result)
