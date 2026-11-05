"""Live-document owner identity for the snapshot ring.

FreeCAD reuses an internal document name after that document is closed, and an
opened copy shares the source document's ``Uid``. Neither value identifies the
live document that owns a snapshot.

When ``collaborationIdentity()`` exists, the owner key is
``(document_uid, document_instance_id)``. That instance id stays on the same
document through edits and in-place ``load``, and a new document receives a
new one.

Stock FreeCAD has no ``collaborationIdentity()``. The fallback key is a random
token stored for this process on the live ``App.Document`` object itself.
``id()`` is not that key: after a close it is reused by a later document, while
the document object is not. A strong map from the object to the token survives
in-place ``load`` (the wrapper is the same object) and an opened copy (a
different object, so it has no token). ``slotDeletedDocument`` drops the entry.
The map sits on the FreeCAD module so an addon reload does not forget tokens
already issued. Rows written with no owner fields match nothing: a name-only
row cannot be told from a closed document after the name is reused.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from contextlib import suppress
from typing import cast

_LOCAL: dict[object, str] = {}
_REGISTRY_NAME = "_mcp_snapshot_owners"
_OBSERVER_NAME = "_mcp_snapshot_owner_observer"


def document_uid(document: object) -> str:
    uid = getattr(document, "Uid", None)
    if uid is None:
        return ""
    value = getattr(uid, "Value", uid)
    if isinstance(value, str):
        return value.strip()
    text = str(value or "").strip()
    return "" if text == "None" else text


def _native_reader(document: object) -> Callable[[], object] | None:
    reader = getattr(document, "collaborationIdentity", None)
    if not callable(reader):
        return None
    return cast(Callable[[], object], reader)


def document_instance_id(document: object) -> int | None:
    reader = _native_reader(document)
    if reader is None:
        return None
    identity = reader()
    if not isinstance(identity, dict):
        return None
    raw = identity.get("instance_id")
    if type(raw) is not int:
        return None
    return raw


def _freecad_module() -> object | None:
    try:
        import FreeCAD
    except ImportError:
        return None
    return FreeCAD


def _ensure_observer(freecad: object) -> None:
    if getattr(freecad, _OBSERVER_NAME, None) is not None:
        return
    add_observer = getattr(freecad, "addDocumentObserver", None)
    if not callable(add_observer):
        return

    class _SnapshotOwnerObserver:
        def slotDeletedDocument(self, document: object) -> None:
            registry = getattr(freecad, _REGISTRY_NAME, None)
            if isinstance(registry, dict):
                with suppress(Exception):
                    registry.pop(document, None)

    observer = _SnapshotOwnerObserver()
    try:
        add_observer(observer)
    except Exception:
        return
    try:
        setattr(freecad, _OBSERVER_NAME, observer)
    except Exception:
        return


def _registry() -> dict[object, str]:
    freecad = _freecad_module()
    if freecad is None:
        return _LOCAL
    current = getattr(freecad, _REGISTRY_NAME, None)
    if not isinstance(current, dict):
        current = {}
        try:
            setattr(freecad, _REGISTRY_NAME, current)
        except Exception:
            return _LOCAL
    _ensure_observer(freecad)
    return current


def _assign_owner_token(document: object) -> str:
    registry = _registry()
    current = registry.get(document)
    if isinstance(current, str) and current:
        return current
    token = uuid.uuid4().hex
    registry[document] = token
    return token


def _owner_token(document: object) -> str | None:
    current = _registry().get(document)
    if isinstance(current, str) and current:
        return current
    return None


def _require_name_and_uid(document: object) -> tuple[str, str]:
    uid = document_uid(document)
    name = getattr(document, "Name", None)
    if not isinstance(name, str) or not name.strip() or not uid:
        raise RuntimeError(
            "snapshot owner requires the live document uid and collaboration instance id"
        )
    return name, uid


def snapshot_owner_fields(document: object) -> dict[str, str | int]:
    """Return the ring fields that identify the live document being snapshotted."""

    name, uid = _require_name_and_uid(document)
    if _native_reader(document) is not None:
        instance_id = document_instance_id(document)
        if instance_id is None:
            raise RuntimeError(
                "snapshot owner requires the live document uid and collaboration instance id"
            )
        return {
            "doc": name,
            "document_uid": uid,
            "document_instance_id": instance_id,
        }
    return {
        "doc": name,
        "document_uid": uid,
        "document_owner_token": _assign_owner_token(document),
    }


def row_belongs_to_document(row: object, document: object) -> bool:
    """True when ``row`` was captured from this live document, not a namesake."""

    if not isinstance(row, dict):
        return False
    uid = document_uid(document)
    if _native_reader(document) is not None:
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
    token = _owner_token(document)
    row_token = row.get("document_owner_token")
    if (
        not isinstance(token, str)
        or not token
        or not isinstance(row_token, str)
        or row_token != token
    ):
        return False
    row_uid = row.get("document_uid")
    if uid:
        return isinstance(row_uid, str) and row_uid == uid
    return row_uid in (None, "")
