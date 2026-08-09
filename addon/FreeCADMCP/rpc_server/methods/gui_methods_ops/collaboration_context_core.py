"""Identity and explicit-document helpers for personal contexts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _member(container: Any, name: str) -> Any:
    if isinstance(container, Mapping):
        return container[name]
    return getattr(container, name)


def collaborators(facade: Any) -> Any:
    value = getattr(facade, "_gui_collaborators", None)
    if value is None:
        raise RuntimeError("actor-scoped GUI collaborators are unavailable")
    return value


def request_actor(facade: Any) -> str:
    identity = _member(collaborators(facade), "get_request_identity")()
    session_id = (
        identity.get("authenticated_session_id")
        if isinstance(identity, Mapping)
        else getattr(identity, "authenticated_session_id", None)
    )
    runtime_id = (
        identity.get("instance_id")
        if isinstance(identity, Mapping)
        else getattr(identity, "instance_id", None)
    )
    if not session_id or not runtime_id:
        raise PermissionError(
            "an authenticated MCP runtime identity is required for GUI views"
        )
    return str(runtime_id)


def _documents(facade: Any) -> list[Any]:
    documents = _member(collaborators(facade), "freecad").listDocuments()
    if isinstance(documents, Mapping):
        return list(documents.values())
    return list(documents or [])


def _document_name(document: Any) -> str:
    name = getattr(document, "Name", None) or getattr(document, "name", None)
    if not name:
        raise ValueError("open document has no stable name")
    return str(name)


def _hinted_document(documents: list[Any], hint: Any) -> Any:
    target = str(hint)
    matches = [
        document
        for document in documents
        if target
        in {
            _document_name(document),
            str(getattr(document, "Label", "")),
        }
    ]
    if len(matches) != 1:
        raise ValueError("requested document is unavailable or ambiguous")
    return matches[0]


def _active_actor_document(facade: Any, actor: str, documents: list[Any]) -> Any:
    registry = _member(collaborators(facade), "personal_view_registry")
    active_name = registry.current_target(actor)
    if not active_name:
        return None
    return next(
        (document for document in documents if _document_name(document) == active_name),
        None,
    )


_ACTIVE_TARGET_OVERLAY = {
    "identifier": "freecad-mcp:active-target",
    "kind": "coin-v1",
    "payload": "Separator { }",
}


def _has_active_target_marker(context: Any) -> bool:
    if not isinstance(context, Mapping):
        return False
    return _ACTIVE_TARGET_OVERLAY in context.get("temporary_overlays", ())


def _with_active_target_marker(
    context: Mapping[str, Any], active: bool
) -> dict[str, Any]:
    updated = dict(context)
    overlays = [
        dict(overlay)
        for overlay in context.get("temporary_overlays", ())
        if overlay != _ACTIVE_TARGET_OVERLAY
    ]
    if active:
        overlays.append(dict(_ACTIVE_TARGET_OVERLAY))
    updated["temporary_overlays"] = overlays
    return updated


def _native_active_actor_document(facade: Any, actor: str, documents: list[Any]) -> Any:
    snapshot = _member(collaborators(facade), "snapshot_personal_view_context")
    marked = [
        candidate
        for candidate in documents
        if _has_active_target_marker(snapshot(_document_name(candidate), actor))
    ]
    if len(marked) != 1:
        return None
    document = marked[0]
    _member(collaborators(facade), "personal_view_registry").activate(
        actor, _document_name(document)
    )
    return document


def activate_personal_target(facade: Any, actor: str, document: Any) -> None:
    """Persist one actor-scoped active document without touching native globals."""

    collabs = collaborators(facade)
    selected_name = _document_name(document)
    registry = _member(collabs, "personal_view_registry")
    prior_target = registry.current_target(actor)
    snapshot = _member(collabs, "snapshot_personal_view_context")
    store = _member(collabs, "store_personal_view_context")
    updates = []
    for candidate in _documents(facade):
        candidate_name = _document_name(candidate)
        context = snapshot(candidate_name, actor)
        if not isinstance(context, Mapping):
            continue
        marked = _with_active_target_marker(
            context, active=candidate_name == selected_name
        )
        if marked != context:
            updates.append((candidate_name, dict(context), marked))
    applied = []
    primary_error = None
    try:
        for candidate_name, prior, marked in updates:
            store(candidate_name, actor, marked)
            applied.append((candidate_name, prior))
        registry.activate(actor, selected_name)
    except Exception as exc:
        primary_error = exc
        raise
    finally:
        if primary_error is not None:
            for candidate_name, prior in reversed(applied):
                try:
                    store(candidate_name, actor, prior)
                except Exception as restore_error:
                    primary_error.add_note(
                        f"active-target context rollback also failed: {restore_error}"
                    )
            try:
                registry.restore_target(actor, prior_target)
            except Exception as restore_error:
                primary_error.add_note(
                    f"active-target registry rollback also failed: {restore_error}"
                )


def _remembered_documents(facade: Any, actor: str, documents: list[Any]) -> list[Any]:
    snapshot = _member(collaborators(facade), "snapshot_personal_view_context")
    return [
        candidate
        for candidate in documents
        if snapshot(_document_name(candidate), actor)
    ]


def resolve_document(facade: Any, actor: str, hint: Any = None) -> Any:
    documents = _documents(facade)
    if not documents:
        raise ValueError("no open documents are available")
    if hint is not None and str(hint):
        return _hinted_document(documents, hint)
    active = _active_actor_document(facade, actor, documents)
    if active is not None:
        return active
    native_active = _native_active_actor_document(facade, actor, documents)
    if native_active is not None:
        return native_active
    remembered = _remembered_documents(facade, actor, documents)
    if len(remembered) == 1:
        return remembered[0]
    if len(remembered) > 1:
        raise ValueError("actor has view state in multiple open documents")
    if len(documents) == 1:
        return documents[0]
    raise ValueError("document hint is required when multiple documents are open")


def redacted_error(facade: Any, exc: Exception) -> str:
    collabs = collaborators(facade)
    _member(collabs, "reraise_if_cancelled")(exc)
    return str(_member(collabs, "redact_rpc_diagnostic")(exc))


__all__ = [
    "_document_name",
    "_member",
    "activate_personal_target",
    "collaborators",
    "redacted_error",
    "request_actor",
    "resolve_document",
]
