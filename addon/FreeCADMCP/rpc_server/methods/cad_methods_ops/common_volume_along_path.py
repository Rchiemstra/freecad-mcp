"""Typed ``common_volume_along_path`` query handler."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from ...._shared.protocol.common_volume_along_path_contract import (
    CommonVolumeAlongPathCollaborators,
    CommonVolumeAlongPathFailure,
    CommonVolumeAlongPathRequest,
    CommonVolumeAlongPathResult,
    DocumentName,
    make_common_volume_along_path_failure,
    make_common_volume_along_path_success,
)
from . import measure_io_actions
from .policy_runtime import app_from, lookup_document, lookup_object, optional_recompute
from .typed_runtime import as_float, as_int, as_str


class CommonVolumeAlongPathError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _failure(error: CommonVolumeAlongPathError, *, retry_safe: bool = True) -> CommonVolumeAlongPathFailure:
    return make_common_volume_along_path_failure(error.code, str(error), retry_safe=retry_safe)


def build_common_volume_along_path_request(
    doc_name: object,
    moving_object: object,
    obstacle_objects: object,
    path_object: object,
    sample_count: object,
    samples: object,
    volume_threshold_mm3: object,
    stop_on_first_hit: object,
) -> CommonVolumeAlongPathRequest | CommonVolumeAlongPathFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(CommonVolumeAlongPathError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(moving_object, str) or not moving_object.strip():
        return _failure(CommonVolumeAlongPathError("INVALID_ARGUMENT", "moving_object must be a nonempty string"))
    if not isinstance(obstacle_objects, list) or not obstacle_objects or any(
        not isinstance(item, str) for item in obstacle_objects
    ):
        return _failure(
            CommonVolumeAlongPathError("INVALID_ARGUMENT", "obstacle_objects must be a nonempty list of strings")
        )
    obstacle_objects_value = obstacle_objects
    if path_object is None:
        path_object_value: str | None = None
    elif not isinstance(path_object, str):
        return _failure(CommonVolumeAlongPathError("INVALID_ARGUMENT", "path_object must be a string or null"))
    else:
        path_object_value = path_object
    if sample_count is None:
        sample_count_value = 12
    elif isinstance(sample_count, bool) or not isinstance(sample_count, int):
        return _failure(CommonVolumeAlongPathError("INVALID_ARGUMENT", "sample_count must be an integer"))
    else:
        sample_count_value = sample_count
    if samples is None:
        samples_value: list[dict[str, object]] | None = None
    elif not isinstance(samples, list):
        return _failure(CommonVolumeAlongPathError("INVALID_ARGUMENT", "samples must be a list"))
    else:
        parsed: list[dict[str, object]] = []
        for item in samples:
            if not isinstance(item, dict) or any(not isinstance(key, str) for key in item):
                return _failure(CommonVolumeAlongPathError("INVALID_ARGUMENT", "samples entries must be objects"))
            parsed.append({str(key): value for key, value in item.items()})
        samples_value = parsed
    if volume_threshold_mm3 is None:
        volume_threshold_mm3_value = float(1e-6)
    elif isinstance(volume_threshold_mm3, bool) or not isinstance(volume_threshold_mm3, (int, float)):
        return _failure(CommonVolumeAlongPathError("INVALID_ARGUMENT", "volume_threshold_mm3 must be a number"))
    else:
        volume_threshold_mm3_value = float(volume_threshold_mm3)
    if stop_on_first_hit is None:
        stop_on_first_hit_value = False
    elif not isinstance(stop_on_first_hit, bool):
        return _failure(CommonVolumeAlongPathError("INVALID_ARGUMENT", "stop_on_first_hit must be a boolean"))
    else:
        stop_on_first_hit_value = stop_on_first_hit
    return CommonVolumeAlongPathRequest(
        doc_name=DocumentName(doc_name),
        moving_object=moving_object,
        obstacle_objects=obstacle_objects_value,
        path_object=path_object_value,
        sample_count=sample_count_value,
        samples=samples_value,
        volume_threshold_mm3=volume_threshold_mm3_value,
        stop_on_first_hit=stop_on_first_hit_value,
    )


def run_common_volume_along_path(
    collaborators: CommonVolumeAlongPathCollaborators,
    doc_name: str,
    moving_object: str,
    obstacle_objects: list[str],
    path_object: str | None = None,
    sample_count: int = 12,
    samples: list[dict[str, object]] | None = None,
    volume_threshold_mm3: float = 1e-6,
    stop_on_first_hit: bool = False,
) -> CommonVolumeAlongPathResult:
    request = build_common_volume_along_path_request(
        doc_name,
        moving_object,
        obstacle_objects,
        path_object,
        sample_count,
        samples,
        volume_threshold_mm3,
        stop_on_first_hit,
    )
    if isinstance(request, dict):
        return request
    app = app_from(collaborators)
    if app is None:
        return _failure(CommonVolumeAlongPathError("FREECAD_UNAVAILABLE", "FreeCAD collaborator is missing"))
    document = lookup_document(app, str(request.doc_name))
    if document is None:
        return _failure(
            CommonVolumeAlongPathError("DOCUMENT_NOT_FOUND", f"Document not found: {request.doc_name!r}")
        )
    if lookup_object(document, request.moving_object) is None:
        return _failure(CommonVolumeAlongPathError("OBJECT_NOT_FOUND", "Object not found"))
    for obstacle_name in request.obstacle_objects:
        if lookup_object(document, obstacle_name) is None:
            return _failure(CommonVolumeAlongPathError("OBJECT_NOT_FOUND", "Object not found"))
    if request.path_object is not None and lookup_object(document, request.path_object) is None:
        return _failure(CommonVolumeAlongPathError("OBJECT_NOT_FOUND", "Object not found"))
    optional_recompute(collaborators, document)
    try:
        payload = measure_io_actions.common_volume_along_path(
            document,
            moving_object=request.moving_object,
            obstacle_objects=request.obstacle_objects,
            path_object=request.path_object,
            sample_count=request.sample_count,
            samples=request.samples,
            volume_threshold_mm3=request.volume_threshold_mm3,
            stop_on_first_hit=request.stop_on_first_hit,
        )
    except Exception as exc:
        return _failure(
            CommonVolumeAlongPathError("COMMON_VOLUME_ALONG_PATH_FAILED", str(exc) or type(exc).__name__)
        )
    samples_raw = payload.get("samples")
    return make_common_volume_along_path_success(
        moving_object=as_str(payload["moving_object"]),
        sample_count=as_int(payload["sample_count"]),
        volume_threshold_mm3=as_float(payload["volume_threshold_mm3"]),
        max_common_volume_mm3=as_float(payload["max_common_volume_mm3"]),
        any_collision=bool(payload["any_collision"]),
        samples=list(samples_raw) if isinstance(samples_raw, list) else [],
    )


class _CommonVolumeAlongPathRpcFacade(Protocol):
    _cad_collaborators: CommonVolumeAlongPathCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_common_volume_along_path(
    self: _CommonVolumeAlongPathRpcFacade,
    doc_name: str,
    moving_object: str,
    obstacle_objects: list[str],
    path_object: str | None = None,
    sample_count: int = 12,
    samples: list[dict[str, object]] | None = None,
    volume_threshold_mm3: float = 1e-6,
    stop_on_first_hit: bool = False,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_common_volume_along_path(
            collaborators,
            doc_name,
            moving_object,
            obstacle_objects,
            path_object,
            sample_count,
            samples,
            volume_threshold_mm3,
            stop_on_first_hit,
        )
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("common_volume_along_path", rpc_common_volume_along_path)


__all__ = [
    "CommonVolumeAlongPathCollaborators",
    "CommonVolumeAlongPathError",
    "build_common_volume_along_path_request",
    "rpc_common_volume_along_path",
    "run_common_volume_along_path",
    "TYPED_RPC_HANDLER",
]
