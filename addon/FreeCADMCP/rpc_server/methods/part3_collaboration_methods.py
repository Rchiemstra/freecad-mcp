"""Part 3 identity-bound checked-edit RPC methods."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

try:
    from ...part3_collaboration.checked_edit_fence import (
        discard_begin_fence,
        pop_begin_fence,
        store_begin_fence,
    )
    from ...part3_collaboration.identity import (
        bootstrap_identity_selector,
        resolve_identity_bound_document,
    )
    from ...part3_collaboration.revisions import (
        conflict_payload_from_commit_result,
        encode_semantic_revision_key,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from addon.FreeCADMCP.part3_collaboration.checked_edit_fence import (
        discard_begin_fence,
        pop_begin_fence,
        store_begin_fence,
    )
    from addon.FreeCADMCP.part3_collaboration.identity import (
        bootstrap_identity_selector,
        resolve_identity_bound_document,
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


def _actor_from_session(self) -> tuple[str | None, dict[str, Any] | None]:
    identity = self._execution_collaborators.request_identity_provider().get_request_identity()
    actor_id = identity.get("authenticated_session_id")
    if not actor_id:
        return None, _error(
            "LEASE_PROTOCOL_REQUIRED",
            "This operation requires a handshake_v2 session and an immutable authenticated request envelope",
        )
    return str(actor_id), None


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


def _session_still_active(document: Any, session_id: str) -> bool:
    status = getattr(document, "editSessionStatus", None)
    if not callable(status):
        return False
    observed = status(session_id)
    if observed is None:
        return False
    if isinstance(observed, Mapping):
        return str(observed.get("status") or "") == "Active"
    return False


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


def begin_checked_edit(self, doc_selector, revision_keys):
    actor_id, auth_failure = _actor_from_session(self)
    if auth_failure is not None:
        return auth_failure

    freecad = self._execution_collaborators.freecad
    document, failure = resolve_identity_bound_document(
        freecad,
        _selector_dict(doc_selector),
    )
    if failure is not None:
        return failure

    begin = getattr(document, "beginEditSession", None)
    snapshot_for_edit = getattr(document, "snapshotForEdit", None)
    if not callable(begin) or not callable(snapshot_for_edit):
        return _error(
            "NATIVE_COLLABORATION_UNAVAILABLE",
            "document does not expose beginEditSession/snapshotForEdit",
        )

    keys = _normalize_revision_keys(revision_keys)
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
    return {
        "success": True,
        "session_id": session_id,
        "document_uid": selector.document_uid,
        "document_instance_id": int(snapshot.get("document_instance_id") or selector.document_instance_id),
        "lifecycle_epoch": int(snapshot.get("lifecycle_epoch") or selector.lifecycle_epoch),
        "document_name": selector.document_name,
        "revisions": list(snapshot.get("revisions") or []),
    }


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
    actor_id, auth_failure = _actor_from_session(self)
    if auth_failure is not None:
        return auth_failure

    if not operation_id:
        return _error("OPERATION_ID_REQUIRED", "operation_id is required")

    freecad = self._execution_collaborators.freecad
    document, failure = resolve_identity_bound_document(
        freecad,
        _selector_dict(doc_selector),
    )
    if failure is not None:
        return failure

    if not _session_still_active(document, str(session_id)):
        discard_begin_fence(str(session_id))
        return _error(
            "DOCUMENT_LIFECYCLE_REJECTED",
            "checked edit session is absent or no longer active",
            session_id=str(session_id),
        )

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
        return _error("CHECKED_PROPERTY_COMMIT_FAILED", str(exc))

    if not isinstance(result, Mapping):
        return _error(
            "CHECKED_PROPERTY_COMMIT_FAILED",
            "commitEdit returned an invalid payload",
        )

    status = str(result.get("status") or "")
    if status == "Conflict":
        return conflict_payload_from_commit_result(result, operation_id=str(operation_id))

    if not bool(result.get("committed")):
        return _error(
            "CHECKED_PROPERTY_COMMIT_REJECTED",
            str(result.get("message") or "commitEdit was not committed"),
            operation_id=str(operation_id),
            status=status,
        )

    published = list(result.get("published_revisions") or [])
    return {
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


def cancel_checked_edit(self, session_id, reason="cancelled by caller"):
    actor_id, auth_failure = _actor_from_session(self)
    if auth_failure is not None:
        return auth_failure

    freecad = self._execution_collaborators.freecad
    documents = list(freecad.listDocuments().values())
    cancel = None
    target_document = None
    for document in documents:
        candidate = getattr(document, "cancelEdit", None)
        if not callable(candidate):
            continue
        if _session_still_active(document, str(session_id)):
            cancel = candidate
            target_document = document
            break

    if cancel is None or target_document is None:
        return _error(
            "DOCUMENT_LIFECYCLE_REJECTED",
            "checked edit session is absent or no longer active",
            session_id=str(session_id),
        )

    try:
        cancelled = bool(cancel(str(session_id), str(reason)))
    except Exception as exc:
        return _error("CHECKED_EDIT_CANCEL_FAILED", str(exc))

    discard_begin_fence(str(session_id))
    return {
        "success": cancelled,
        "cancelled": cancelled,
        "session_id": str(session_id),
    }


__all__ = [
    "begin_checked_edit",
    "cancel_checked_edit",
    "commit_checked_property",
    "get_semantic_revisions",
]
