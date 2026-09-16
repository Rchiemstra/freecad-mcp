from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .types.part3_identity_selector import Part3IdentitySelector


def _error(code: str, message: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "success": False,
        "ok": False,
        "error_code": code,
        "error": message,
    }
    payload.update(extra)
    return payload


def _document_uid(document: Any) -> str:
    uid = getattr(document, "Uid", None)
    if uid is None:
        return ""
    value = getattr(uid, "Value", uid)
    return str(value or "")


def _read_identity(document: Any) -> dict[str, Any] | None:
    reader = getattr(document, "collaborationIdentity", None)
    if not callable(reader):
        return None
    identity = reader()
    if not isinstance(identity, Mapping):
        return None
    return dict(identity)


def bootstrap_identity_selector(document: Any) -> Part3IdentitySelector:
    identity = _read_identity(document)
    if identity is None:
        raise TypeError("document must expose collaborationIdentity()")
    return Part3IdentitySelector(
        document_uid=_document_uid(document),
        document_instance_id=int(identity.get("instance_id") or 0),
        lifecycle_epoch=int(identity.get("lifecycle_epoch") or 0),
        document_name=str(getattr(document, "Name", "") or "") or None,
    )


def selector_from_mapping(selector: Mapping[str, Any] | None) -> Part3IdentitySelector | None:
    if not isinstance(selector, Mapping):
        return None
    uid = str(selector.get("document_uid") or "")
    instance_id = selector.get("document_instance_id")
    lifecycle_epoch = selector.get("lifecycle_epoch")
    if not uid or instance_id is None or lifecycle_epoch is None:
        return None
    document_name = selector.get("document_name")
    return Part3IdentitySelector(
        document_uid=uid,
        document_instance_id=int(instance_id),
        lifecycle_epoch=int(lifecycle_epoch),
        document_name=str(document_name) if document_name else None,
    )


def resolve_identity_bound_document(
    freecad: Any,
    selector: Mapping[str, Any] | None,
) -> tuple[Any | None, dict[str, Any] | None]:
    parsed = selector_from_mapping(selector)
    if parsed is None:
        return None, _error(
            "DOCUMENT_NOT_FOUND",
            "Part 3 identity selector requires document_uid, document_instance_id, and lifecycle_epoch",
        )

    list_documents = getattr(freecad, "listDocuments", None)
    if not callable(list_documents):
        return None, _error("DOCUMENT_NOT_FOUND", "FreeCAD listDocuments is unavailable")

    matches: list[Any] = []
    for document in list_documents().values():
        if _document_uid(document) == parsed.document_uid:
            matches.append(document)

    if not matches:
        return None, _error(
            "DOCUMENT_NOT_FOUND",
            "no live document matches the Part 3 selector uid",
        )
    if len(matches) > 1:
        return None, _error(
            "DOCUMENT_SELECTOR_CONFLICT",
            "multiple live documents match the Part 3 selector uid",
        )

    document = matches[0]
    identity = _read_identity(document)
    if identity is None:
        return None, _error(
            "NATIVE_COLLABORATION_UNAVAILABLE",
            "document does not expose collaborationIdentity()",
        )

    live_instance_id = int(identity.get("instance_id") or 0)
    live_lifecycle_epoch = int(identity.get("lifecycle_epoch") or 0)
    live_state = str(identity.get("state") or "")

    if (
        live_instance_id != parsed.document_instance_id
        or live_lifecycle_epoch != parsed.lifecycle_epoch
    ):
        return None, _error(
            "DOCUMENT_LIFECYCLE_REJECTED",
            "document lifecycle changed",
            expected_lifecycle_epoch=parsed.lifecycle_epoch,
            current_lifecycle_epoch=live_lifecycle_epoch,
            expected_document_instance_id=parsed.document_instance_id,
            current_document_instance_id=live_instance_id,
        )

    if live_state != "Live":
        return None, _error(
            "DOCUMENT_LIFECYCLE_REJECTED",
            "document is not live",
            state=live_state,
        )

    return document, None
