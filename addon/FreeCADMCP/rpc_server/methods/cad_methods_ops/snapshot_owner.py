"""Live-document owner identity for the snapshot ring.

FreeCAD reuses an internal document name after that document is closed, and an
opened copy shares the source document's ``Uid``. Neither value identifies the
live document that owns a snapshot. The collaboration instance id stays on that
same document through edits and in-place ``load``, and a new document receives
a new one.
"""

from __future__ import annotations


def document_uid(document: object) -> str:
    uid = getattr(document, "Uid", None)
    if uid is None:
        return ""
    value = getattr(uid, "Value", uid)
    if isinstance(value, str):
        return value.strip()
    text = str(value or "").strip()
    return "" if text == "None" else text


def document_instance_id(document: object) -> int | None:
    reader = getattr(document, "collaborationIdentity", None)
    if not callable(reader):
        return None
    identity = reader()
    if not isinstance(identity, dict):
        return None
    raw = identity.get("instance_id")
    if type(raw) is not int:
        return None
    return raw


def snapshot_owner_fields(document: object) -> dict[str, str | int]:
    """Return the ring fields that identify the live document being snapshotted."""

    uid = document_uid(document)
    instance_id = document_instance_id(document)
    name = getattr(document, "Name", None)
    if not isinstance(name, str) or not name.strip() or not uid or instance_id is None:
        raise RuntimeError(
            "snapshot owner requires the live document uid and collaboration instance id"
        )
    return {
        "doc": name,
        "document_uid": uid,
        "document_instance_id": instance_id,
    }


def row_belongs_to_document(row: object, document: object) -> bool:
    """True when ``row`` was captured from this live document, not a namesake."""

    if not isinstance(row, dict):
        return False
    uid = document_uid(document)
    instance_id = document_instance_id(document)
    if not uid or instance_id is None:
        return False
    row_uid = row.get("document_uid")
    row_instance = row.get("document_instance_id")
    return (
        isinstance(row_uid, str)
        and row_uid == uid
        and type(row_instance) is int
        and row_instance == instance_id
    )
