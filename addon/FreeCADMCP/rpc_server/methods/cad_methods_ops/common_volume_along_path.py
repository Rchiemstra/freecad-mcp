"""Typed ``common_volume_along_path`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.common_volume_along_path_contract import (
    DocumentName,
    CommonVolumeAlongPathCollaborators,
    CommonVolumeAlongPathFailure,
    CommonVolumeAlongPathRequest,
    CommonVolumeAlongPathResult,
    MutationDocument,
    MutationObject,
    MutationReadDocument,
    make_common_volume_along_path_failure,
    make_common_volume_along_path_success,
    make_common_volume_along_path_uncertain,
)
from .typed_runtime import as_float, as_int, as_str
from . import measure_io_actions
from .common_volume_along_path_mutation import CommonVolumeAlongPathError, run_common_volume_along_path_native_mutation


@dataclass(frozen=True, slots=True)
class CommonVolumeAlongPathReceipt:
    payload: dict[str, object]
    obj: MutationObject | None


@dataclass(frozen=True, slots=True)
class CommonVolumeAlongPathInspection:
    payload: dict[str, object]


def _failure(error: CommonVolumeAlongPathError, *, retry_safe: bool = True) -> CommonVolumeAlongPathFailure:
    return make_common_volume_along_path_failure(error.code, str(error), retry_safe=retry_safe)


def build_common_volume_along_path_request(
    doc_name: object, moving_object: object, obstacle_objects: object, path_object: object, sample_count: object, samples: object, volume_threshold_mm3: object, stop_on_first_hit: object
) -> CommonVolumeAlongPathRequest | CommonVolumeAlongPathFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(CommonVolumeAlongPathError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(moving_object, str) or not moving_object.strip():
        return _failure(CommonVolumeAlongPathError("INVALID_ARGUMENT", "moving_object must be a nonempty string"))
    if not isinstance(obstacle_objects, list) or not obstacle_objects or any(not isinstance(item, str) for item in obstacle_objects):
        return _failure(CommonVolumeAlongPathError("INVALID_ARGUMENT", "obstacle_objects must be a nonempty list of strings"))
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
    request = CommonVolumeAlongPathRequest(
        doc_name=DocumentName(doc_name),
        moving_object=moving_object,
        obstacle_objects=obstacle_objects_value,
        path_object=path_object_value,
        sample_count=sample_count_value,
        samples=samples_value,
        volume_threshold_mm3=volume_threshold_mm3_value,
        stop_on_first_hit=stop_on_first_hit_value
    )
    return request


@dataclass(slots=True)
class _CommonVolumeAlongPathExecution:
    collaborators: CommonVolumeAlongPathCollaborators
    request: CommonVolumeAlongPathRequest
    created: CommonVolumeAlongPathReceipt | None = None
    inspected: CommonVolumeAlongPathInspection | None = None

    def apply(self, doc: MutationDocument) -> None:
        self.created = apply_common_volume_along_path(doc, self.request)

    def inspect(self, doc: MutationReadDocument) -> None:
        if self.created is None:
            raise CommonVolumeAlongPathError(
                "INVALID_COMMON_VOLUME_ALONG_PATH_RESULT",
                "common_volume_along_path did not return an identity receipt",
            )
        self.inspected = read_common_volume_along_path_result(doc, self.created, self.request)

    def run(self) -> CommonVolumeAlongPathResult:
        result = run_common_volume_along_path_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_common_volume_along_path_uncertain(
                "COMMON_VOLUME_ALONG_PATH_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected common_volume_along_path result",
                committed=True,
            )
        payload = self.inspected.payload
        samples_raw = payload.get("samples")
        return make_common_volume_along_path_success(
            moving_object=as_str(payload["moving_object"]),
            sample_count=as_int(payload["sample_count"]),
            volume_threshold_mm3=as_float(payload["volume_threshold_mm3"]),
            max_common_volume_mm3=as_float(payload["max_common_volume_mm3"]),
            any_collision=bool(payload["any_collision"]),
            samples=list(samples_raw) if isinstance(samples_raw, list) else [],
        )


def apply_common_volume_along_path(doc: MutationDocument, request: CommonVolumeAlongPathRequest) -> CommonVolumeAlongPathReceipt:
    """Apply common_volume_along_path without recomputing or managing a transaction."""

    obj = doc.getObject(request.moving_object)
    if obj is None:
        raise CommonVolumeAlongPathError("OBJECT_NOT_FOUND", "Object not found")
    return CommonVolumeAlongPathReceipt(payload={"object": obj.Name}, obj=obj)



def read_common_volume_along_path_result(
    doc: MutationReadDocument, receipt: CommonVolumeAlongPathReceipt, request: CommonVolumeAlongPathRequest
) -> CommonVolumeAlongPathInspection:
    payload = measure_io_actions.common_volume_along_path(doc, moving_object=request.moving_object, obstacle_objects=request.obstacle_objects, path_object=request.path_object, sample_count=request.sample_count, samples=request.samples, volume_threshold_mm3=request.volume_threshold_mm3, stop_on_first_hit=request.stop_on_first_hit)
    return CommonVolumeAlongPathInspection(payload=payload)



def run_common_volume_along_path(
    collaborators: CommonVolumeAlongPathCollaborators,
    doc_name: str, moving_object: str, obstacle_objects: list[str], path_object: str | None = None, sample_count: int = 12, samples: list[dict[str, object]] | None = None, volume_threshold_mm3: float = 1e-6, stop_on_first_hit: bool = False,
) -> CommonVolumeAlongPathResult:
    """Run common_volume_along_path through apply, recompute, inspection, and commit."""

    request = build_common_volume_along_path_request(doc_name, moving_object, obstacle_objects, path_object, sample_count, samples, volume_threshold_mm3, stop_on_first_hit)
    if isinstance(request, dict):
        return request
    return _CommonVolumeAlongPathExecution(collaborators, request).run()


class _CommonVolumeAlongPathRpcFacade(Protocol):
    _cad_collaborators: CommonVolumeAlongPathCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_common_volume_along_path(
    self: _CommonVolumeAlongPathRpcFacade,
    doc_name: str, moving_object: str, obstacle_objects: list[str], path_object: str | None = None, sample_count: int = 12, samples: list[dict[str, object]] | None = None, volume_threshold_mm3: float = 1e-6, stop_on_first_hit: bool = False,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_common_volume_along_path(collaborators, doc_name, moving_object, obstacle_objects, path_object, sample_count, samples, volume_threshold_mm3, stop_on_first_hit)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("common_volume_along_path", rpc_common_volume_along_path)


__all__ = [
    "CommonVolumeAlongPathCollaborators",
    "CommonVolumeAlongPathError",
    "CommonVolumeAlongPathInspection",
    "CommonVolumeAlongPathReceipt",
    "apply_common_volume_along_path",
    "build_common_volume_along_path_request",
    "read_common_volume_along_path_result",
    "rpc_common_volume_along_path",
    "run_common_volume_along_path",
    "TYPED_RPC_HANDLER",
]
