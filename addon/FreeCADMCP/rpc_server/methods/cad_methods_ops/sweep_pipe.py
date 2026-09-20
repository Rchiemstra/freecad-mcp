
"""Typed ``sweep_pipe`` mutation."""
from __future__ import annotations

from .typed_rpc_support import (
    as_float,
    assign_attr,
    invoke,
    nonempty_string,
    object_label,
    object_name,
    object_type_id,
    optional_string,
    require_object,
    resolve_if_exists,
)
from .typed_rpc_container_support import (
    add_named_object,
    add_to_container,
)

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

try:
    from ...._shared.protocol.sweep_pipe_contract import (
        SweepPipeCollaborators,
        SweepPipeDocument,
        SweepPipeFailure,
        SweepPipeName,
        SweepPipeReadDocument,
        SweepPipeRequest,
        SweepPipeResult,
        DocumentName,
        make_sweep_pipe_failure,
        make_sweep_pipe_success,
        make_sweep_pipe_uncertain,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.sweep_pipe_contract import (
        SweepPipeCollaborators,
        SweepPipeDocument,
        SweepPipeFailure,
        SweepPipeName,
        SweepPipeReadDocument,
        SweepPipeRequest,
        SweepPipeResult,
        DocumentName,
        make_sweep_pipe_failure,
        make_sweep_pipe_success,
        make_sweep_pipe_uncertain,
    )
from .sweep_pipe_mutation import SweepPipeError, run_sweep_pipe_native_mutation
from .typed_runtime import TypedMutationError, is_derived_from, load_module, module_callable


_ALLOWED_PROFILE_MODES = frozenset({"frenet"})


@dataclass(frozen=True, slots=True)
class SweepPipeReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    item: object | None
    skipped: bool = False
    extra: object = None


@dataclass(frozen=True, slots=True)
class SweepPipeInspection:
    """Read-only data captured after the native-owned recompute."""

    name: SweepPipeName
    label: str
    extra: object = None


def _failure(error: SweepPipeError, *, retry_safe: bool = True) -> SweepPipeFailure:
    return make_sweep_pipe_failure(error.code, str(error), retry_safe=retry_safe)


def _validate_color(color: object) -> list[float] | None:
    if color is None:
        return None
    if not isinstance(color, Sequence) or isinstance(color, (str, bytes)):
        raise SweepPipeError("INVALID_ARGUMENT", "color must be a sequence of 3 numbers in [0, 1] or None")
    if len(color) != 3:
        raise SweepPipeError("INVALID_ARGUMENT", "color must be a sequence of 3 numbers in [0, 1] or None")
    values: list[float] = []
    for item in color:
        if not isinstance(item, (int, float)) or isinstance(item, bool):
            raise SweepPipeError("INVALID_ARGUMENT", "color must be a sequence of 3 numbers in [0, 1] or None")
        value = float(item)
        if value < 0.0 or value > 1.0:
            raise SweepPipeError("INVALID_ARGUMENT", "color must be a sequence of 3 numbers in [0, 1] or None")
        values.append(value)
    return values


def _path_wire_shape(path_obj: object) -> object:
    shape = getattr(path_obj, "Shape", None)
    if shape is None:
        raise SweepPipeError("INVALID_ARGUMENT", "path_wire has no Shape")
    is_null = getattr(shape, "isNull", None)
    if callable(is_null):
        try:
            if bool(is_null()):
                raise SweepPipeError("INVALID_ARGUMENT", "path_wire Shape is null")
        except SweepPipeError:
            raise
        except Exception:
            pass
    wires = list(getattr(shape, "Wires", None) or [])
    if wires:
        return wires[0]
    edges = list(getattr(shape, "Edges", None) or [])
    if not edges:
        raise SweepPipeError("INVALID_ARGUMENT", "path_wire has no edges or wires")
    try:
        part = load_module("Part")
        return module_callable(part, "Wire")(edges)
    except TypedMutationError:
        return shape


def _shape_is_null(shape: object) -> bool:
    is_null = getattr(shape, "isNull", None)
    if callable(is_null):
        try:
            return bool(is_null())
        except Exception:
            return False
    return False


def _shape_has_positive_volume(shape: object) -> bool:
    solids = list(getattr(shape, "Solids", None) or [])
    for solid in solids:
        volume = getattr(solid, "Volume", None)
        if isinstance(volume, (int, float)) and not isinstance(volume, bool) and float(volume) > 0.0:
            return True
    volume = getattr(shape, "Volume", None)
    return isinstance(volume, (int, float)) and not isinstance(volume, bool) and float(volume) > 0.0


def _shape_has_faces_with_area(shape: object) -> bool:
    faces = list(getattr(shape, "Faces", None) or [])
    if not faces:
        return False
    area = getattr(shape, "Area", None)
    return isinstance(area, (int, float)) and not isinstance(area, bool) and float(area) > 0.0


def _try_make_solid(shape: object) -> object:
    if shape is None or _shape_is_null(shape):
        return shape
    if _shape_has_positive_volume(shape):
        return shape

    make_solid_method = getattr(shape, "makeSolid", None)
    if callable(make_solid_method):
        try:
            solidified = invoke(make_solid_method)
            if solidified is not None and not _shape_is_null(solidified) and _shape_has_positive_volume(solidified):
                return solidified
        except Exception:
            pass

    faces = list(getattr(shape, "Faces", None) or [])
    if faces:
        try:
            part = load_module("Part")
            shell_fn = module_callable(part, "Shell")
            solid_fn = module_callable(part, "Solid")
            shell = invoke(shell_fn, faces)
            solid = invoke(solid_fn, shell)
            if solid is not None and not _shape_is_null(solid) and _shape_has_positive_volume(solid):
                return solid
        except Exception:
            pass

    solids = list(getattr(shape, "Solids", None) or [])
    for solid in solids:
        if _shape_has_positive_volume(solid):
            return solid

    return shape


def _fuse_shapes(shapes: list[object]) -> object | None:
    fused: object | None = None
    for shape in shapes:
        if shape is None or _shape_is_null(shape):
            continue
        if fused is None:
            fused = shape
            continue
        fuse = getattr(fused, "fuse", None)
        if not callable(fuse):
            return None
        try:
            fused = invoke(fuse, shape)
        except Exception:
            return None
    return fused


def _edge_endpoints(edge: object) -> tuple[object, object] | None:
    verts = list(getattr(edge, "Vertexes", None) or [])
    if len(verts) >= 2:
        start = getattr(verts[0], "Point", None)
        end = getattr(verts[1], "Point", None)
        if start is not None and end is not None:
            return start, end
    value_at = getattr(edge, "valueAt", None)
    first = getattr(edge, "FirstParameter", None)
    last = getattr(edge, "LastParameter", None)
    if callable(value_at) and first is not None and last is not None:
        try:
            start = invoke(value_at, first)
            end = invoke(value_at, last)
        except Exception:
            return None
        if start is not None and end is not None:
            return start, end
    return None


def _cylinders_along_path(part: object, path_wire: object, radius: float) -> object | None:
    make_cylinder = getattr(part, "makeCylinder", None)
    if not callable(make_cylinder):
        return None
    solids: list[object] = []
    for edge in list(getattr(path_wire, "Edges", None) or []):
        ends = _edge_endpoints(edge)
        if ends is None:
            continue
        start, end = ends
        sub = getattr(end, "sub", None)
        if not callable(sub):
            continue
        try:
            direction = invoke(sub, start)
        except Exception:
            continue
        length = getattr(direction, "Length", None)
        if not isinstance(length, (int, float)) or isinstance(length, bool) or float(length) <= 0.0:
            continue
        try:
            cylinder = invoke(make_cylinder, radius, float(length), start, direction)
        except Exception:
            continue
        if cylinder is not None:
            solids.append(cylinder)
    return _fuse_shapes(solids)


def _tubes_along_path(part: object, path_wire: object, radius: float) -> object | None:
    make_tube = getattr(part, "makeTube", None)
    if not callable(make_tube):
        return None
    tubes: list[object] = []
    for edge in list(getattr(path_wire, "Edges", None) or []):
        try:
            tube = invoke(make_tube, edge, radius)
        except Exception:
            continue
        if tube is not None:
            tubes.append(tube)
    return _fuse_shapes(tubes)


def _circle_profile_at_path_start(part: object, path_wire: object, radius: float) -> object | None:
    make_circle = getattr(part, "makeCircle", None)
    wire_cls = getattr(part, "Wire", None)
    if not callable(make_circle) or not callable(wire_cls):
        return None
    edges = list(getattr(path_wire, "Edges", None) or [])
    if not edges:
        return None
    edge = edges[0]
    ends = _edge_endpoints(edge)
    center = ends[0] if ends is not None else None
    tangent_at = getattr(edge, "tangentAt", None)
    first = getattr(edge, "FirstParameter", None)
    normal = None
    if callable(tangent_at) and first is not None:
        try:
            normal = invoke(tangent_at, first)
        except Exception:
            normal = None
    try:
        if center is not None and normal is not None:
            circle = invoke(make_circle, radius, center, normal)
        else:
            circle = invoke(make_circle, radius)
        return invoke(wire_cls, [circle])
    except Exception:
        return None


def _make_pipe_solid(path_wire: object, diameter_mm: float) -> object | None:
    try:
        part = load_module("Part")
    except TypedMutationError:
        return None
    radius = diameter_mm / 2.0
    last_exc: Exception | None = None
    hollow_fallback: object | None = None

    def consider(candidate: object) -> object | None:
        nonlocal hollow_fallback
        if candidate is None or _shape_is_null(candidate):
            return None
        finalized = _try_make_solid(candidate)
        if _shape_has_positive_volume(finalized):
            return finalized
        if hollow_fallback is None and _shape_has_faces_with_area(finalized):
            hollow_fallback = finalized
        return None

    make_tube_method = getattr(path_wire, "makeTube", None)
    if callable(make_tube_method):
        try:
            solid = consider(invoke(make_tube_method, radius))
            if solid is not None:
                return solid
        except Exception as exc:
            last_exc = exc

    make_tube_fn = getattr(part, "makeTube", None)
    if callable(make_tube_fn):
        for args in (
            (radius, path_wire),
            (radius, 0.0, path_wire),
            (path_wire, radius),
        ):
            try:
                solid = consider(invoke(make_tube_fn, *args))
                if solid is not None:
                    return solid
            except Exception as extra_exc:
                last_exc = extra_exc

    make_pipe = getattr(path_wire, "makePipe", None)
    if callable(make_pipe):
        try:
            make_circle = module_callable(part, "makeCircle")
            profile = make_circle(radius)
            for profile_arg in (profile, module_callable(part, "Edge")(profile)):
                try:
                    solid = consider(invoke(make_pipe, profile_arg))
                    if solid is not None:
                        return solid
                except Exception as extra_exc:
                    last_exc = extra_exc
        except Exception as extra_exc:
            last_exc = extra_exc

    try:
        solid = consider(_cylinders_along_path(part, path_wire, radius))
        if solid is not None:
            return solid
    except Exception as extra_exc:
        last_exc = extra_exc

    make_pipe_shell = getattr(path_wire, "makePipeShell", None)
    if callable(make_pipe_shell):
        try:
            profile = _circle_profile_at_path_start(part, path_wire, radius)
            if profile is not None:
                pipe_shell_args: tuple[object, ...]
                for pipe_shell_args in (
                    ([profile],),
                    ([profile], True, True),
                    ([profile], True, False),
                ):
                    try:
                        solid = consider(invoke(make_pipe_shell, *pipe_shell_args))
                        if solid is not None:
                            return solid
                    except Exception as extra_exc:
                        last_exc = extra_exc
        except Exception as extra_exc:
            last_exc = extra_exc

    try:
        solid = consider(_tubes_along_path(part, path_wire, radius))
        if solid is not None:
            return solid
    except Exception as extra_exc:
        last_exc = extra_exc

    if hollow_fallback is not None:
        return hollow_fallback
    if last_exc is not None:
        raise SweepPipeError("SWEEP_PIPE_FAILED", str(last_exc))
    return None


def _set_shape_color(item: object, color: list[float]) -> None:
    view = getattr(item, "ViewObject", None)
    if view is None:
        return
    for attr in ("ShapeColor", "LineColor"):
        if hasattr(view, attr):
            assign_attr(view, attr, tuple(color))
            return


def _solid_has_volume(shape: object) -> bool:
    if shape is None or _shape_is_null(shape):
        return False
    if _shape_has_positive_volume(shape):
        return True
    return _shape_has_faces_with_area(shape)


def apply_sweep_pipe(doc: SweepPipeDocument, request: SweepPipeRequest) -> SweepPipeReceipt:
    """Create a swept solid without recomputing."""

    skipped = resolve_if_exists(doc, request.solid_name, request.if_exists, error=SweepPipeError)
    if skipped is not None:
        return SweepPipeReceipt(name=object_name(skipped) or request.solid_name, item=skipped, skipped=True)
    path_obj = require_object(doc, request.path_wire, missing_code="OBJECT_NOT_FOUND", error=SweepPipeError)
    path_shape = _path_wire_shape(path_obj)
    solid_shape = _make_pipe_solid(path_shape, request.diameter_mm)
    created = add_named_object(doc, "Part::Feature", request.solid_name)
    if solid_shape is not None:
        assign_attr(created, "Shape", solid_shape)
    color = _validate_color(request.color)
    if color is not None:
        _set_shape_color(created, color)
    if request.container:
        container = require_object(
            doc,
            request.container,
            missing_code="OBJECT_NOT_FOUND",
            error=SweepPipeError,
        )
        add_to_container(container, created)
    return SweepPipeReceipt(name=object_name(created) or request.solid_name, item=created, skipped=False)


def read_sweep_pipe_result(doc: SweepPipeReadDocument, receipt: SweepPipeReceipt) -> SweepPipeInspection:
    """Build the public result after the shared mutation recompute."""

    located: object | None = doc.getObject(receipt.name)
    if located is None:
        raise SweepPipeError("CREATED_OBJECT_MISSING", f"Target is missing: {receipt.name!r}")
    if receipt.item is not None and located is not receipt.item:
        raise SweepPipeError("CREATED_OBJECT_REPLACED", f"Target was replaced before commit: {receipt.name!r}")

    type_id = object_type_id(located)
    if "Part::Feature" not in type_id and not is_derived_from(located, "Part::Feature"):
        raise SweepPipeError("CREATED_OBJECT_WRONG_TYPE", f"Created object is not Part::Feature: {receipt.name!r}")

    shape = getattr(located, "Shape", None)
    if shape is not None and not _solid_has_volume(shape):
        raise SweepPipeError("CREATED_OBJECT_INVALID", f"Created solid has no volume: {receipt.name!r}")
    extra = dict(receipt.extra) if isinstance(receipt.extra, dict) else {}
    if shape is not None:
        try:
            extra["volume_mm3"] = float(getattr(shape, "Volume", 0.0) or 0.0)
        except Exception:
            extra["volume_mm3"] = 0.0

    return SweepPipeInspection(
        name=SweepPipeName(receipt.name),
        label=object_label(located),
        extra=extra,
    )


def build_sweep_pipe_request(doc_name: object, path_wire: object, diameter_mm: object, solid_name: object, profile_mode: object, color: object, container: object, if_exists: object) -> SweepPipeRequest | SweepPipeFailure:
    doc_name_value = nonempty_string(doc_name, "doc_name")
    if doc_name_value is None:
        return _failure(SweepPipeError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    path_wire_value = nonempty_string(path_wire, "path_wire")
    if path_wire_value is None:
        return _failure(SweepPipeError("INVALID_ARGUMENT", "path_wire must be a nonempty string"))
    diameter_mm_value = as_float(diameter_mm, None)
    if diameter_mm_value is None:
        return _failure(SweepPipeError("INVALID_ARGUMENT", "diameter_mm must be a number"))
    if diameter_mm_value <= 0.0:
        return _failure(SweepPipeError("INVALID_ARGUMENT", "diameter_mm must be greater than 0"))
    solid_name_value = nonempty_string(solid_name, "solid_name")
    if solid_name_value is None:
        return _failure(SweepPipeError("INVALID_ARGUMENT", "solid_name must be a nonempty string"))
    profile_mode_value = nonempty_string(profile_mode, "profile_mode")
    if profile_mode_value is None:
        return _failure(SweepPipeError("INVALID_ARGUMENT", "profile_mode must be a nonempty string"))
    if profile_mode_value not in _ALLOWED_PROFILE_MODES:
        return _failure(
            SweepPipeError(
                "INVALID_ARGUMENT",
                f"profile_mode must be one of: {', '.join(sorted(_ALLOWED_PROFILE_MODES))}",
            )
        )
    try:
        _validate_color(color)
    except SweepPipeError as exc:
        return _failure(exc)
    if container is None:
        container_value: str | None = None
    else:
        container_value = optional_string(container)
        if container_value is None:
            return _failure(SweepPipeError("INVALID_ARGUMENT", "container must be a nonempty string or None"))
    if_exists_value = nonempty_string(if_exists, "if_exists")
    if if_exists_value is None:
        return _failure(SweepPipeError("INVALID_ARGUMENT", "if_exists must be a nonempty string"))
    if if_exists_value not in {"error", "skip", "replace"}:
        return _failure(SweepPipeError("INVALID_ARGUMENT", "if_exists must be one of: error, skip, replace"))
    return SweepPipeRequest(
        doc_name=DocumentName(doc_name_value),
        path_wire=path_wire_value,
        diameter_mm=diameter_mm_value,
        solid_name=solid_name_value,
        profile_mode=profile_mode_value,
        color=color,
        container=container_value,
        if_exists=if_exists_value,
    )


@dataclass(slots=True)
class _SweepPipeExecution:
    collaborators: SweepPipeCollaborators
    request: SweepPipeRequest
    created: SweepPipeReceipt | None = None
    inspected: SweepPipeInspection | None = None

    def apply(self, doc: SweepPipeDocument) -> None:
        self.created = apply_sweep_pipe(doc, self.request)

    def inspect(self, doc: SweepPipeReadDocument) -> None:
        if self.created is None:
            raise SweepPipeError(
                "INVALID_SWEEP_PIPE_RESULT",
                "sweep_pipe did not return an identity receipt",
            )
        self.inspected = read_sweep_pipe_result(doc, self.created)

    def run(self) -> SweepPipeResult:
        result = run_sweep_pipe_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_sweep_pipe_uncertain(
                "SWEEP_PIPE_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected result",
                committed=True,
            )
        success = dict(make_sweep_pipe_success(solid_name=self.inspected.name))
        extra = self.inspected.extra
        if isinstance(extra, dict):
            for key, value in extra.items():
                if isinstance(key, str) and key not in success:
                    success[key] = value
        return success  # type: ignore[return-value]


def run_sweep_pipe(
    collaborators: SweepPipeCollaborators,
    doc_name: object, path_wire: object, diameter_mm: object, solid_name: object, profile_mode: object, color: object, container: object, if_exists: object,
) -> SweepPipeResult:
    """Run the mutation through apply, recompute, inspection, and commit."""

    request = build_sweep_pipe_request(doc_name, path_wire, diameter_mm, solid_name, profile_mode, color, container, if_exists)
    if isinstance(request, dict):
        return request
    return _SweepPipeExecution(collaborators, request).run()


class _SweepPipeRpcFacade(Protocol):
    _cad_collaborators: SweepPipeCollaborators

    def _dispatch_gui(self, callback: Callable[[], object], timeout: int | None = None) -> object: ...


def rpc_sweep_pipe(
    self: _SweepPipeRpcFacade, doc_name: str, path_wire: str, diameter_mm: float, solid_name: str, profile_mode: str = "frenet", color: object = None, container: str | None = None, if_exists: str = "error",
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_sweep_pipe(collaborators, doc_name, path_wire, diameter_mm, solid_name, profile_mode, color, container, if_exists)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("sweep_pipe", rpc_sweep_pipe)


__all__ = [
    "SweepPipeCollaborators",
    "SweepPipeError",
    "SweepPipeInspection",
    "SweepPipeReceipt",
    "apply_sweep_pipe",
    "build_sweep_pipe_request",
    "read_sweep_pipe_result",
    "rpc_sweep_pipe",
    "run_sweep_pipe",
    "TYPED_RPC_HANDLER",
]
