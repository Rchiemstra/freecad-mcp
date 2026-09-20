"""Typed ``get_objects`` query handler."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Protocol

try:
    from ...._shared.protocol.get_objects_contract import (
        ALLOWED_FIELDS,
        DEFAULT_FIELDS,
        DEFAULT_PAGE_SIZE,
        MAX_PAGE_PAYLOAD_BYTES,
        MAX_PAGE_SIZE,
        MIN_PAGE_SIZE,
        DocumentName,
        GetObjectsCollaborators,
        GetObjectsFailure,
        GetObjectsRequest,
        GetObjectsResult,
        compute_snapshot_id,
        decode_cursor,
        encode_cursor,
        make_get_objects_failure,
        make_get_objects_success,
        parse_get_objects_response,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.get_objects_contract import (
        ALLOWED_FIELDS,
        DEFAULT_FIELDS,
        DEFAULT_PAGE_SIZE,
        MAX_PAGE_PAYLOAD_BYTES,
        MAX_PAGE_SIZE,
        MIN_PAGE_SIZE,
        DocumentName,
        GetObjectsCollaborators,
        GetObjectsFailure,
        GetObjectsRequest,
        GetObjectsResult,
        compute_snapshot_id,
        decode_cursor,
        encode_cursor,
        make_get_objects_failure,
        make_get_objects_success,
        parse_get_objects_response,
    )
from ...serialize import project_listing_object
from .policy_runtime import app_from, lookup_document


class GetObjectsError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _failure(error: GetObjectsError, *, retry_safe: bool = True) -> GetObjectsFailure:
    return make_get_objects_failure(error.code, str(error), retry_safe=retry_safe)


def _normalize_fields(fields: object) -> tuple[str, ...] | GetObjectsFailure:
    if fields is None:
        return DEFAULT_FIELDS
    if not isinstance(fields, list) or not fields:
        return _failure(
            GetObjectsError("INVALID_ARGUMENT", "fields must be a nonempty list")
        )
    normalized: list[str] = []
    for entry in fields:
        if not isinstance(entry, str) or not entry.strip():
            return _failure(
                GetObjectsError("INVALID_ARGUMENT", "fields entries must be strings")
            )
        if entry not in ALLOWED_FIELDS:
            return _failure(
                GetObjectsError("INVALID_ARGUMENT", f"unknown field: {entry!r}")
            )
        if entry not in normalized:
            normalized.append(entry)
    return tuple(normalized)


def _normalize_include_properties(
    include_properties: object,
) -> tuple[str, ...] | GetObjectsFailure | None:
    if include_properties is None:
        return None
    if not isinstance(include_properties, list):
        return _failure(
            GetObjectsError(
                "INVALID_ARGUMENT",
                "include_properties must be a list of strings",
            )
        )
    normalized: list[str] = []
    for entry in include_properties:
        if not isinstance(entry, str) or not entry.strip():
            return _failure(
                GetObjectsError(
                    "INVALID_ARGUMENT",
                    "include_properties entries must be strings",
                )
            )
        if entry not in normalized:
            normalized.append(entry)
    return tuple(normalized)


def build_get_objects_request(
    doc_name: object,
    fields: object = None,
    include_properties: object = None,
    include_shape: object = False,
    include_view: object = False,
    page_size: object = DEFAULT_PAGE_SIZE,
    cursor: object = None,
) -> GetObjectsRequest | GetObjectsFailure:
    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(
            GetObjectsError("INVALID_ARGUMENT", "doc_name must be a nonempty string")
        )
    normalized_fields = _normalize_fields(fields)
    if isinstance(normalized_fields, dict):
        return normalized_fields
    normalized_properties = _normalize_include_properties(include_properties)
    if isinstance(normalized_properties, dict):
        return normalized_properties
    if type(include_shape) is not bool:
        return _failure(
            GetObjectsError("INVALID_ARGUMENT", "include_shape must be a boolean")
        )
    if type(include_view) is not bool:
        return _failure(
            GetObjectsError("INVALID_ARGUMENT", "include_view must be a boolean")
        )
    if (
        type(page_size) is not int
        or page_size < MIN_PAGE_SIZE
        or page_size > MAX_PAGE_SIZE
    ):
        return _failure(
            GetObjectsError(
                "INVALID_ARGUMENT",
                (
                    "page_size must be an integer between "
                    f"{MIN_PAGE_SIZE} and {MAX_PAGE_SIZE}"
                ),
            )
        )
    if cursor is not None and (not isinstance(cursor, str) or not cursor.strip()):
        return _failure(
            GetObjectsError("INVALID_ARGUMENT", "cursor must be a nonempty string")
        )
    return GetObjectsRequest(
        doc_name=DocumentName(doc_name),
        fields=normalized_fields,
        include_properties=normalized_properties,
        include_shape=include_shape,
        include_view=include_view,
        page_size=page_size,
        cursor=cursor if isinstance(cursor, str) else None,
    )


def _object_names(document: object) -> list[str]:
    objects = getattr(document, "Objects", None)
    if not isinstance(objects, list):
        return []
    names = [str(getattr(obj, "Name", "")) for obj in objects]
    return sorted(name for name in names if name)


def _serialize_row(
    document: object,
    name: str,
    request: GetObjectsRequest,
) -> dict[str, object]:
    getter = getattr(document, "getObject", None)
    obj = getter(name) if callable(getter) else None
    if obj is None:
        return {
            "Name": name,
            "error": f"Object not found during listing: {name!r}",
        }
    try:
        return project_listing_object(
            obj,
            fields=request.fields,
            include_properties=request.include_properties,
            include_shape=request.include_shape,
            include_view=request.include_view,
        )
    except Exception as exc:
        return {
            "Name": str(getattr(obj, "Name", name)),
            "Label": getattr(obj, "Label", "<unknown>"),
            "TypeId": getattr(obj, "TypeId", "<unknown>"),
            "error": f"Serialization failed: {exc}",
        }


def run_get_objects(
    collaborators: GetObjectsCollaborators,
    doc_name: object,
    fields: object = None,
    include_properties: object = None,
    include_shape: object = False,
    include_view: object = False,
    page_size: object = DEFAULT_PAGE_SIZE,
    cursor: object = None,
) -> GetObjectsResult:
    request = build_get_objects_request(
        doc_name,
        fields,
        include_properties,
        include_shape,
        include_view,
        page_size,
        cursor,
    )
    if isinstance(request, dict):
        return request
    app = app_from(collaborators)
    if app is None:
        return _failure(
            GetObjectsError("FREECAD_UNAVAILABLE", "FreeCAD collaborator is missing")
        )
    document = lookup_document(app, str(request.doc_name))
    if document is None or not document:
        return _failure(
            GetObjectsError(
                "DOCUMENT_NOT_FOUND",
                f"Document not found: {request.doc_name!r}",
            )
        )

    names = _object_names(document)
    snapshot_id = compute_snapshot_id(str(request.doc_name), names)
    offset = 0
    if request.cursor is not None:
        decoded = decode_cursor(request.cursor)
        if decoded is None:
            return _failure(GetObjectsError("INVALID_CURSOR", "cursor is invalid"))
        cursor_snapshot_id, cursor_offset = decoded
        if cursor_snapshot_id != snapshot_id:
            return _failure(
                GetObjectsError(
                    "STALE_CURSOR",
                    "document object set changed since cursor was issued",
                ),
                retry_safe=True,
            )
        if cursor_offset > len(names):
            return _failure(
                GetObjectsError("INVALID_CURSOR", "cursor offset is out of range")
            )
        offset = cursor_offset

    page_names = names[offset : offset + request.page_size]
    objects = [_serialize_row(document, name, request) for name in page_names]
    total_count = len(names)
    returned_count = len(page_names)
    next_offset = offset + returned_count
    complete = next_offset >= total_count
    next_cursor = None if complete else encode_cursor(snapshot_id, next_offset)

    result = make_get_objects_success(
        doc_name=str(request.doc_name),
        objects=objects,
        total_count=total_count,
        returned_count=returned_count,
        page_size=request.page_size,
        complete=complete,
        next_cursor=next_cursor,
        snapshot_id=snapshot_id,
    )
    encoded = json.dumps(result, ensure_ascii=False, default=str)
    if len(encoded) > MAX_PAGE_PAYLOAD_BYTES:
        return _failure(
            GetObjectsError(
                "PAYLOAD_TOO_LARGE",
                "get_objects page exceeds payload cap; reduce page_size or projection",
            ),
            retry_safe=False,
        )
    return result


def _normalize_dispatch_result(raw: object) -> GetObjectsResult:
    if isinstance(raw, dict):
        return parse_get_objects_response(raw)
    return parse_get_objects_response(raw)


class _GetObjectsRpcFacade(Protocol):
    _cad_collaborators: GetObjectsCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_get_objects(
    self: _GetObjectsRpcFacade,
    doc_name: str,
    fields: object = None,
    include_properties: object = None,
    include_shape: bool = False,
    include_view: bool = False,
    page_size: int = DEFAULT_PAGE_SIZE,
    cursor: object = None,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_get_objects(
            collaborators,
            doc_name,
            fields,
            include_properties,
            include_shape,
            include_view,
            page_size,
            cursor,
        )
    )
    normalized = _normalize_dispatch_result(res)
    return dict(normalized)


TYPED_RPC_HANDLER = ("get_objects", rpc_get_objects)


__all__ = [
    "TYPED_RPC_HANDLER",
    "GetObjectsCollaborators",
    "GetObjectsError",
    "build_get_objects_request",
    "rpc_get_objects",
    "run_get_objects",
]
