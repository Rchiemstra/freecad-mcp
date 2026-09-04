"""Part 3 identity-bound checked-edit RPC methods."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

try:
    from part3_collaboration.admission import (
        actor_from_session,
        early_operation_replay,
        early_operation_replay_across_documents,
        replay_or_protocol_error,
    )
    from part3_collaboration.checked_edit_fence import (
        discard_begin_fence,
        pop_begin_fence,
        store_begin_fence,
    )
    from part3_collaboration.identity import (
        bootstrap_identity_selector,
        resolve_identity_bound_document,
    )
    from part3_collaboration.operation_terminal_store import store_operation_terminal
    from part3_collaboration.revisions import (
        conflict_payload_from_commit_result,
        encode_semantic_revision_key,
    )
except ImportError:  # pragma: no cover - package test layout
    from addon.FreeCADMCP.part3_collaboration.admission import (
        actor_from_session,
        early_operation_replay,
        early_operation_replay_across_documents,
        replay_or_protocol_error,
    )
    from addon.FreeCADMCP.part3_collaboration.checked_edit_fence import (
        discard_begin_fence,
        pop_begin_fence,
        store_begin_fence,
    )
    from addon.FreeCADMCP.part3_collaboration.identity import (
        bootstrap_identity_selector,
        resolve_identity_bound_document,
    )
    from addon.FreeCADMCP.part3_collaboration.operation_terminal_store import (
        store_operation_terminal,
    )
    from addon.FreeCADMCP.part3_collaboration.revisions import (
        conflict_payload_from_commit_result,
        encode_semantic_revision_key,
    )

_COLLABORATIVE_SET_PROPERTY = "App.CollaborativeSetProperty"


def _error(code: str, message: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "success": False,
        "ok": False,
        "error_code": code,
        "error": message,
    }
    payload.update(extra)
    return payload


def _normalize_revision_keys(revision_keys: Sequence[Mapping[str, Any]] | None) -> list[dict[str, str]]:
    if revision_keys is None:
        return []
    normalized: list[dict[str, str]] = []
    for item in revision_keys:
        if not isinstance(item, Mapping):
            continue
        kind = str(item.get("kind") or "")
        if not kind:
            continue
        entry: dict[str, str] = {"kind": kind}
        subject = item.get("subject")
        if subject is not None:
            entry["subject"] = str(subject)
        property_name = item.get("property_name")
        if property_name is not None:
            entry["property_name"] = str(property_name)
        normalized.append(entry)
    return normalized


def _selector_dict(selector: Any) -> Mapping[str, Any] | None:
    if isinstance(selector, Mapping):
        return selector
    return None


def _active_session_owner(document: Any, session_id: str) -> tuple[bool, str | None]:
    status = getattr(document, "editSessionStatus", None)
    if not callable(status):
        return False, None
    observed = status(session_id)
    if observed is None:
        return False, None
    if isinstance(observed, Mapping):
        if str(observed.get("status") or "") != "Active":
            return False, None
        actor_id = observed.get("actor_id")
        return True, str(actor_id) if actor_id else None
    return False, None


def _actor_mismatch(session_id: str) -> dict[str, Any]:
    return _error(
        "CHECKED_EDIT_ACTOR_MISMATCH",
        "checked edit session does not belong to this authenticated MCP runtime",
        session_id=str(session_id),
    )


def _store_terminal(
    actor_id: str,
    operation_id: str,
    canonical_payload: Mapping[str, Any],
    document: Any,
    terminal_result: Mapping[str, Any],
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


def get_semantic_revisions(self, doc_selector, revision_keys):
    freecad = self._execution_collaborators.freecad
    document, failure = resolve_identity_bound_document(
        freecad,
        _selector_dict(doc_selector),
    )
    if failure is not None:
        return failure

    capture = getattr(document, "captureSemanticRevisions", None)
    if not callable(capture):
        return _error(
            "NATIVE_COLLABORATION_UNAVAILABLE",
            "document does not expose captureSemanticRevisions()",
        )

    try:
        snapshot = capture(_normalize_revision_keys(revision_keys))
    except Exception as exc:
        return _error("SEMANTIC_REVISION_CAPTURE_FAILED", str(exc))

    if not isinstance(snapshot, Mapping):
        return _error(
            "SEMANTIC_REVISION_CAPTURE_FAILED",
            "captureSemanticRevisions returned an invalid payload",
        )

    revisions = list(snapshot.get("revisions") or [])
    selector = bootstrap_identity_selector(document)
    return {
        "success": True,
        "document_uid": selector.document_uid,
        "document_instance_id": int(snapshot.get("document_instance_id") or selector.document_instance_id),
        "lifecycle_epoch": int(snapshot.get("lifecycle_epoch") or selector.lifecycle_epoch),
        "document_name": selector.document_name,
        "revisions": revisions,
    }


def begin_checked_edit(self, doc_selector, revision_keys, operation_id):
    if not operation_id:
        return _error("OPERATION_ID_REQUIRED", "operation_id is required")

    freecad = self._execution_collaborators.freecad
    document, failure = resolve_identity_bound_document(
        freecad,
        _selector_dict(doc_selector),
    )
    if failure is not None:
        return failure

    keys = _normalize_revision_keys(revision_keys)
    canonical_payload = {
        "method": "begin_checked_edit",
        "doc_selector": dict(_selector_dict(doc_selector) or {}),
        "revision_keys": keys,
    }
    replay, auth_failure = early_operation_replay(
        self,
        str(operation_id),
        canonical_payload,
        document,
    )
    if auth_failure is not None:
        return auth_failure
    replay_result = replay_or_protocol_error(replay)
    if replay_result is not None:
        return replay_result

    actor_id, auth_failure = actor_from_session(self)
    if auth_failure is not None:
        return auth_failure

    begin = getattr(document, "beginEditSession", None)
    snapshot_for_edit = getattr(document, "snapshotForEdit", None)
    if not callable(begin) or not callable(snapshot_for_edit):
        return _error(
            "NATIVE_COLLABORATION_UNAVAILABLE",
            "document does not expose beginEditSession/snapshotForEdit",
        )

    try:
        session = begin(actor_id)
        if not isinstance(session, Mapping):
            return _error("CHECKED_EDIT_BEGIN_FAILED", "beginEditSession returned invalid session")
        session_id = str(session.get("session_id") or "")
        if not session_id:
            return _error("CHECKED_EDIT_BEGIN_FAILED", "beginEditSession returned no session_id")
        snapshot = snapshot_for_edit(session_id, keys)
    except Exception as exc:
        return _error("CHECKED_EDIT_BEGIN_FAILED", str(exc))

    if not isinstance(snapshot, Mapping):
        return _error("CHECKED_EDIT_BEGIN_FAILED", "snapshotForEdit returned invalid payload")

    selector = bootstrap_identity_selector(document)
    store_begin_fence(
        session_id,
        document_instance_id=int(
            snapshot.get("document_instance_id") or selector.document_instance_id
        ),
        lifecycle_epoch=int(snapshot.get("lifecycle_epoch") or selector.lifecycle_epoch),
        revisions=list(snapshot.get("revisions") or []),
    )
    result = {
        "success": True,
        "session_id": session_id,
        "operation_id": str(operation_id),
        "document_uid": selector.document_uid,
        "document_instance_id": int(snapshot.get("document_instance_id") or selector.document_instance_id),
        "lifecycle_epoch": int(snapshot.get("lifecycle_epoch") or selector.lifecycle_epoch),
        "document_name": selector.document_name,
        "revisions": list(snapshot.get("revisions") or []),
    }
    _store_terminal(actor_id, str(operation_id), canonical_payload, document, result)
    return result


def commit_checked_property(
    self,
    session_id,
    doc_selector,
    object_name,
    property_name,
    value_type,
    value,
    operation_id,
):
    freecad = self._execution_collaborators.freecad
    document, failure = resolve_identity_bound_document(
        freecad,
        _selector_dict(doc_selector),
    )
    if failure is not None:
        return failure

    canonical_payload = {
        "method": "commit_checked_property",
        "session_id": str(session_id),
        "doc_selector": dict(_selector_dict(doc_selector) or {}),
        "object_name": str(object_name),
        "property_name": str(property_name),
        "value_type": str(value_type),
        "value": str(value),
    }
    replay, auth_failure = early_operation_replay(
        self,
        str(operation_id),
        canonical_payload,
        document,
    )
    if auth_failure is not None:
        return auth_failure
    replay_result = replay_or_protocol_error(replay)
    if replay_result is not None:
        return replay_result

    actor_id, auth_failure = actor_from_session(self)
    if auth_failure is not None:
        return auth_failure

    session_active, session_owner = _active_session_owner(document, str(session_id))
    if not session_active:
        discard_begin_fence(str(session_id))
        return _error(
            "DOCUMENT_LIFECYCLE_REJECTED",
            "checked edit session is absent or no longer active",
            session_id=str(session_id),
        )
    if session_owner != actor_id:
        return _actor_mismatch(str(session_id))

    fence = pop_begin_fence(str(session_id))
    if fence is None:
        return _error(
            "CHECKED_EDIT_FENCE_MISSING",
            "checked edit begin snapshot is missing for this session",
            session_id=str(session_id),
        )

    selector = bootstrap_identity_selector(document)
    if (
        int(selector.document_instance_id) != fence.document_instance_id
        or int(selector.lifecycle_epoch) != fence.lifecycle_epoch
    ):
        return _error(
            "DOCUMENT_LIFECYCLE_REJECTED",
            "checked edit session targets a stale document instance",
            session_id=str(session_id),
        )

    prepare_with_fence = getattr(document, "prepareEditWithExpectedRevisions", None)
    commit = getattr(document, "commitEdit", None)
    if not callable(commit):
        return _error(
            "NATIVE_COLLABORATION_UNAVAILABLE",
            "document does not expose commitEdit",
        )
    if not callable(prepare_with_fence):
        return _error(
            "NATIVE_COLLABORATION_UNAVAILABLE",
            "document does not expose prepareEditWithExpectedRevisions",
        )
    if not fence.revisions:
        return _error(
            "CHECKED_EDIT_FENCE_MISSING",
            "checked edit begin snapshot contained no revision observations",
            session_id=str(session_id),
        )

    arguments = {
        "object": str(object_name),
        "property": str(property_name),
        "value_type": str(value_type),
        "value": str(value),
    }
    try:
        prepared = prepare_with_fence(
            str(session_id),
            str(operation_id),
            _COLLABORATIVE_SET_PROPERTY,
            arguments,
            list(fence.revisions),
            "part3-checked-edit",
        )
        result = commit(str(session_id), prepared)
    except Exception as exc:
        failure = _error("CHECKED_PROPERTY_COMMIT_FAILED", str(exc))
        _store_terminal(actor_id, str(operation_id), canonical_payload, document, failure)
        return failure

    if not isinstance(result, Mapping):
        failure = _error(
            "CHECKED_PROPERTY_COMMIT_FAILED",
            "commitEdit returned an invalid payload",
        )
        _store_terminal(actor_id, str(operation_id), canonical_payload, document, failure)
        return failure

    status = str(result.get("status") or "")
    if status == "Conflict":
        terminal = conflict_payload_from_commit_result(result, operation_id=str(operation_id))
        _store_terminal(actor_id, str(operation_id), canonical_payload, document, terminal)
        return terminal

    if not bool(result.get("committed")):
        failure = _error(
            "CHECKED_PROPERTY_COMMIT_REJECTED",
            str(result.get("message") or "commitEdit was not committed"),
            operation_id=str(operation_id),
            status=status,
        )
        _store_terminal(actor_id, str(operation_id), canonical_payload, document, failure)
        return failure

    published = list(result.get("published_revisions") or [])
    terminal = {
        "success": True,
        "ok": True,
        "committed": True,
        "operation_id": str(operation_id),
        "status": status,
        "published_revisions": published,
        "published_semantic_keys": [
            encode_semantic_revision_key(item)
            for item in published
            if isinstance(item, Mapping)
        ],
    }
    _store_terminal(actor_id, str(operation_id), canonical_payload, document, terminal)
    return terminal


def cancel_checked_edit(self, session_id, reason="cancelled by caller", operation_id=None):
    actor_id, auth_failure = actor_from_session(self)
    if auth_failure is not None:
        return auth_failure
    if not operation_id:
        return _error("OPERATION_ID_REQUIRED", "operation_id is required")

    canonical_payload = {
        "method": "cancel_checked_edit",
        "session_id": str(session_id),
        "reason": str(reason),
    }

    freecad = self._execution_collaborators.freecad
    documents = list(freecad.listDocuments().values())

    replay, auth_failure = early_operation_replay_across_documents(
        self,
        str(operation_id),
        canonical_payload,
        documents,
    )
    if auth_failure is not None:
        return auth_failure
    replay_result = replay_or_protocol_error(replay)
    if replay_result is not None:
        return replay_result

    cancel = None
    target_document = None
    for document in documents:
        session_active, session_owner = _active_session_owner(document, str(session_id))
        if not session_active:
            continue
        if session_owner != actor_id:
            return _actor_mismatch(str(session_id))
        candidate = getattr(document, "cancelEdit", None)
        if not callable(candidate):
            continue
        cancel = candidate
        target_document = document
        break

    if cancel is None or target_document is None:
        failure = _error(
            "DOCUMENT_LIFECYCLE_REJECTED",
            "checked edit session is absent or no longer active",
            session_id=str(session_id),
        )
        if target_document is not None:
            _store_terminal(actor_id, str(operation_id), canonical_payload, target_document, failure)
        return failure

    try:
        cancelled = bool(cancel(str(session_id), str(reason)))
    except Exception as exc:
        failure = _error("CHECKED_EDIT_CANCEL_FAILED", str(exc))
        _store_terminal(actor_id, str(operation_id), canonical_payload, target_document, failure)
        return failure

    discard_begin_fence(str(session_id))
    terminal = {
        "success": cancelled,
        "cancelled": cancelled,
        "session_id": str(session_id),
        "operation_id": str(operation_id),
    }
    _store_terminal(actor_id, str(operation_id), canonical_payload, target_document, terminal)
    return terminal


__all__ = [
    "begin_checked_edit",
    "cancel_checked_edit",
    "commit_checked_property",
    "get_semantic_revisions",
]
