
"""Typed ``create_subshape_binder`` mutation."""
from __future__ import annotations

from .typed_rpc_support import (
    as_bool,
    assign_attr,
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

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.create_subshape_binder_contract import (
    CreateSubshapeBinderCollaborators,
    CreateSubshapeBinderDocument,
    CreateSubshapeBinderFailure,
    CreateSubshapeBinderName,
    CreateSubshapeBinderReadDocument,
    CreateSubshapeBinderRequest,
    CreateSubshapeBinderResult,
    DocumentName,
    make_create_subshape_binder_failure,
    make_create_subshape_binder_success,
    make_create_subshape_binder_uncertain,
)
from .create_subshape_binder_mutation import CreateSubshapeBinderError, run_create_subshape_binder_native_mutation
from .typed_runtime import is_derived_from



@dataclass(frozen=True, slots=True)
class CreateSubshapeBinderReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    item: object | None
    skipped: bool = False
    extra: object = None


@dataclass(frozen=True, slots=True)
class CreateSubshapeBinderInspection:
    """Read-only data captured after the native-owned recompute."""

    name: CreateSubshapeBinderName
    label: str
    extra: object = None


def _failure(error: CreateSubshapeBinderError, *, retry_safe: bool = True) -> CreateSubshapeBinderFailure:
    return make_create_subshape_binder_failure(error.code, str(error), retry_safe=retry_safe)


def _validate_sub_elements(sub_elements: object) -> list[str] | None:
    if sub_elements is None:
        return None
    if not isinstance(sub_elements, list):
        raise CreateSubshapeBinderError("INVALID_ARGUMENT", "sub_elements must be None or a list of nonempty strings")
    validated: list[str] = []
    for index, item in enumerate(sub_elements):
        value = nonempty_string(item, "sub_elements")
        if value is None:
            raise CreateSubshapeBinderError(
                "INVALID_ARGUMENT",
                f"sub_elements[{index}] must be a nonempty string",
            )
        validated.append(value)
    return validated


def _resolve_owner(doc: CreateSubshapeBinderDocument, request: CreateSubshapeBinderRequest) -> object | None:
    if request.target_body:
        return require_object(doc, request.target_body, missing_code="OBJECT_NOT_FOUND", error=CreateSubshapeBinderError)
    if request.target_container:
        return require_object(
            doc,
            request.target_container,
            missing_code="OBJECT_NOT_FOUND",
            error=CreateSubshapeBinderError,
        )
    return None


def _boundbox_values(obj: object) -> tuple[float, float, float, float, float, float] | None:
    shape = getattr(obj, "Shape", None)
    box = getattr(shape, "BoundBox", None) if shape is not None else None
    if box is None:
        return None
    try:
        return (
            float(getattr(box, "XMin", 0.0)),
            float(getattr(box, "YMin", 0.0)),
            float(getattr(box, "ZMin", 0.0)),
            float(getattr(box, "XMax", 0.0)),
            float(getattr(box, "YMax", 0.0)),
            float(getattr(box, "ZMax", 0.0)),
        )
    except Exception:
        return None


def _binder_bbox_extras(doc: CreateSubshapeBinderReadDocument, binder: object) -> dict[str, object]:
    source = None
    support = getattr(binder, "Support", None)
    try:
        values = list(getattr(support, "getValues", lambda: support)() or [])
    except Exception:
        values = list(support) if isinstance(support, (list, tuple)) else []
    if values:
        first = values[0]
        candidate = first[0] if isinstance(first, (list, tuple)) and first else first
        source = candidate if candidate is not None and hasattr(candidate, "Shape") else None
        if source is None and isinstance(candidate, str):
            source = doc.getObject(candidate)
    source_bb = _boundbox_values(source) if source is not None else None
    binder_bb = _boundbox_values(binder)
    delta = None
    if source_bb is not None and binder_bb is not None:
        delta = max(abs(left - right) for left, right in zip(source_bb, binder_bb))
    return {
        "bbox_delta_mm": None if delta is None else round(delta, 6),
        "source_bbox": None if source_bb is None else {
            "xmin": source_bb[0],
            "ymin": source_bb[1],
            "zmin": source_bb[2],
            "xmax": source_bb[3],
            "ymax": source_bb[4],
            "zmax": source_bb[5],
        },
        "binder_bbox": None if binder_bb is None else {
            "xmin": binder_bb[0],
            "ymin": binder_bb[1],
            "zmin": binder_bb[2],
            "xmax": binder_bb[3],
            "ymax": binder_bb[4],
            "zmax": binder_bb[5],
        },
    }


def _object_in_owner(located: object, owner: object) -> bool:
    group = list(getattr(owner, "Group", None) or [])
    if located in group:
        return True
    in_list = list(getattr(located, "InList", None) or [])
    return owner in in_list


def apply_create_subshape_binder(doc: CreateSubshapeBinderDocument, request: CreateSubshapeBinderRequest) -> CreateSubshapeBinderReceipt:
    """Create a SubShapeBinder without recomputing."""

    skipped = resolve_if_exists(doc, request.binder_name, request.if_exists, error=CreateSubshapeBinderError)
    if skipped is not None:
        return CreateSubshapeBinderReceipt(name=object_name(skipped) or request.binder_name, item=skipped, skipped=True)
    owner = _resolve_owner(doc, request)
    source_obj = require_object(doc, request.source_object, missing_code="OBJECT_NOT_FOUND", error=CreateSubshapeBinderError)
    sub_elements = _validate_sub_elements(request.sub_elements)
    created: object | None = None
    factory = getattr(owner, "newObject", None) if owner is not None else None
    if owner is not None and callable(factory):
        try:
            created = factory("PartDesign::SubShapeBinder", request.binder_name)
        except Exception:
            created = None
    if created is None:
        created = add_named_object(doc, "PartDesign::SubShapeBinder", request.binder_name)
        if owner is not None:
            add_to_container(owner, created)
    try:
        if sub_elements:
            support = [(source_obj, tuple(sub_elements))]
        else:
            support = [(source_obj, ("",))]
        assign_attr(created, "Support", support)
        assign_attr(created, "Relative", request.relative)
        bind_mode = "Synchronized" if request.sync_placement else "Frozen"
        assign_attr(created, "BindMode", bind_mode)
        if hasattr(created, "TraceSupport"):
            assign_attr(created, "TraceSupport", request.sync_placement)
    except CreateSubshapeBinderError:
        raise
    except Exception as exc:
        raise CreateSubshapeBinderError("CREATE_SUBSHAPE_BINDER_FAILED", str(exc)) from exc
    owner_name = object_name(owner) if owner is not None else None
    return CreateSubshapeBinderReceipt(
        name=object_name(created) or request.binder_name,
        item=created,
        skipped=False,
        extra={"owner_name": owner_name},
    )


def read_create_subshape_binder_result(doc: CreateSubshapeBinderReadDocument, receipt: CreateSubshapeBinderReceipt) -> CreateSubshapeBinderInspection:
    """Build the public result after the shared mutation recompute."""

    located: object | None = doc.getObject(receipt.name)
    if located is None:
        raise CreateSubshapeBinderError("CREATED_OBJECT_MISSING", f"Target is missing: {receipt.name!r}")
    if receipt.item is not None and located is not receipt.item:
        raise CreateSubshapeBinderError("CREATED_OBJECT_REPLACED", f"Target was replaced before commit: {receipt.name!r}")

    type_id = object_type_id(located)
    if "SubShapeBinder" not in type_id and not is_derived_from(located, "PartDesign::SubShapeBinder"):
        raise CreateSubshapeBinderError(
            "CREATED_OBJECT_WRONG_TYPE",
            f"Created object is not PartDesign::SubShapeBinder: {receipt.name!r}",
        )

    owner_name = None
    extra = dict(receipt.extra) if isinstance(receipt.extra, dict) else {}
    if extra:
        owner_name = extra.get("owner_name")
    if owner_name:
        owner = doc.getObject(str(owner_name))
        if owner is not None and not _object_in_owner(located, owner):
            raise CreateSubshapeBinderError(
                "POSTCONDITION_FAILED",
                f"Binder is not grouped under owner: {owner_name!r}",
            )
    extra.update(_binder_bbox_extras(doc, located))
    return CreateSubshapeBinderInspection(
        name=CreateSubshapeBinderName(receipt.name),
        label=object_label(located),
        extra=extra,
    )


def build_create_subshape_binder_request(doc_name: object, binder_name: object, source_object: object, sub_elements: object, target_body: object, target_container: object, relative: object, sync_placement: object, if_exists: object) -> CreateSubshapeBinderRequest | CreateSubshapeBinderFailure:
    doc_name_value = nonempty_string(doc_name, "doc_name")
    if doc_name_value is None:
        return _failure(CreateSubshapeBinderError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    binder_name_value = nonempty_string(binder_name, "binder_name")
    if binder_name_value is None:
        return _failure(CreateSubshapeBinderError("INVALID_ARGUMENT", "binder_name must be a nonempty string"))
    source_object_value = nonempty_string(source_object, "source_object")
    if source_object_value is None:
        return _failure(CreateSubshapeBinderError("INVALID_ARGUMENT", "source_object must be a nonempty string"))
    try:
        _validate_sub_elements(sub_elements)
    except CreateSubshapeBinderError as exc:
        return _failure(exc)
    if target_body is None:
        target_body_value: str | None = None
    else:
        target_body_value = optional_string(target_body)
        if target_body_value is None:
            return _failure(CreateSubshapeBinderError("INVALID_ARGUMENT", "target_body must be a nonempty string or None"))
    if target_container is None:
        target_container_value: str | None = None
    else:
        target_container_value = optional_string(target_container)
        if target_container_value is None:
            return _failure(CreateSubshapeBinderError("INVALID_ARGUMENT", "target_container must be a nonempty string or None"))
    relative_value = as_bool(relative, False)
    if relative_value is None:
        return _failure(CreateSubshapeBinderError("INVALID_ARGUMENT", "relative must be a boolean"))
    sync_placement_value = as_bool(sync_placement, True)
    if sync_placement_value is None:
        return _failure(CreateSubshapeBinderError("INVALID_ARGUMENT", "sync_placement must be a boolean"))
    if_exists_value = nonempty_string(if_exists, "if_exists")
    if if_exists_value is None:
        return _failure(CreateSubshapeBinderError("INVALID_ARGUMENT", "if_exists must be a nonempty string"))
    if if_exists_value not in {"error", "skip", "replace"}:
        return _failure(CreateSubshapeBinderError("INVALID_ARGUMENT", "if_exists must be one of: error, skip, replace"))
    return CreateSubshapeBinderRequest(
        doc_name=DocumentName(doc_name_value),
        binder_name=binder_name_value,
        source_object=source_object_value,
        sub_elements=sub_elements,
        target_body=target_body_value,
        target_container=target_container_value,
        relative=relative_value,
        sync_placement=sync_placement_value,
        if_exists=if_exists_value,
    )


@dataclass(slots=True)
class _CreateSubshapeBinderExecution:
    collaborators: CreateSubshapeBinderCollaborators
    request: CreateSubshapeBinderRequest
    created: CreateSubshapeBinderReceipt | None = None
    inspected: CreateSubshapeBinderInspection | None = None

    def apply(self, doc: CreateSubshapeBinderDocument) -> None:
        self.created = apply_create_subshape_binder(doc, self.request)

    def inspect(self, doc: CreateSubshapeBinderReadDocument) -> None:
        if self.created is None:
            raise CreateSubshapeBinderError(
                "INVALID_CREATE_SUBSHAPE_BINDER_RESULT",
                "create_subshape_binder did not return an identity receipt",
            )
        self.inspected = read_create_subshape_binder_result(doc, self.created)

    def run(self) -> CreateSubshapeBinderResult:
        result = run_create_subshape_binder_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_create_subshape_binder_uncertain(
                "CREATE_SUBSHAPE_BINDER_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected result",
                committed=True,
            )
        success = dict(make_create_subshape_binder_success(binder_name=self.inspected.name))
        extra = self.inspected.extra
        if isinstance(extra, dict):
            for key, value in extra.items():
                if isinstance(key, str) and key not in success:
                    success[key] = value
        return success  # type: ignore[return-value]


def run_create_subshape_binder(
    collaborators: CreateSubshapeBinderCollaborators,
    doc_name: object, binder_name: object, source_object: object, sub_elements: object, target_body: object, target_container: object, relative: object, sync_placement: object, if_exists: object,
) -> CreateSubshapeBinderResult:
    """Run the mutation through apply, recompute, inspection, and commit."""

    request = build_create_subshape_binder_request(doc_name, binder_name, source_object, sub_elements, target_body, target_container, relative, sync_placement, if_exists)
    if isinstance(request, dict):
        return request
    return _CreateSubshapeBinderExecution(collaborators, request).run()


class _CreateSubshapeBinderRpcFacade(Protocol):
    _cad_collaborators: CreateSubshapeBinderCollaborators

    def _dispatch_gui(self, callback: Callable[[], object], timeout: int | None = None) -> object: ...


def rpc_create_subshape_binder(
    self: _CreateSubshapeBinderRpcFacade, doc_name: str, binder_name: str, source_object: str, sub_elements: object = None, target_body: str | None = None, target_container: str | None = None, relative: bool = False, sync_placement: bool = True, if_exists: str = "error",
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_create_subshape_binder(collaborators, doc_name, binder_name, source_object, sub_elements, target_body, target_container, relative, sync_placement, if_exists)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("create_subshape_binder", rpc_create_subshape_binder)


__all__ = [
    "CreateSubshapeBinderCollaborators",
    "CreateSubshapeBinderError",
    "CreateSubshapeBinderInspection",
    "CreateSubshapeBinderReceipt",
    "apply_create_subshape_binder",
    "build_create_subshape_binder_request",
    "read_create_subshape_binder_result",
    "rpc_create_subshape_binder",
    "run_create_subshape_binder",
    "TYPED_RPC_HANDLER",
]
