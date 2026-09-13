"""Typed ``repair_references`` mutation."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.repair_references_contract import (
    DocumentName,
    ObjectName,
    RepairItem,
    RepairRef,
    RepairReferencesCollaborators,
    RepairReferencesFailure,
    RepairReferencesRequest,
    RepairReferencesResult,
    make_repair_references_failure,
    make_repair_references_success,
    make_repair_references_uncertain,
)
from .repair_references_mutation import (
    RepairReferencesError,
    run_repair_references_native_mutation,
)
from .typed_rpc_document import document_name, get_object


@dataclass(frozen=True, slots=True)
class RepairReferencesReceipt:
    """Internal identity captured while applying the mutation."""

    document_name: str
    repaired: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class RepairReferencesInspection:
    """Read-only data captured after the native-owned recompute."""

    document_name: DocumentName
    repaired_count: int


def _failure(
    error: RepairReferencesError, *, retry_safe: bool = True
) -> RepairReferencesFailure:
    return make_repair_references_failure(
        error.code, str(error), retry_safe=retry_safe, diagnostics=error.diagnostics
    )


def _mapping(raw: object) -> dict[str, object] | None:
    if not isinstance(raw, Mapping):
        return None
    result: dict[str, object] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            return None
        result[key] = value
    return result


def _as_bool(value: object, *, default: bool = False) -> bool | None:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return None


def _parse_refs(raw: object) -> tuple[RepairRef, ...] | RepairReferencesFailure:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return _failure(RepairReferencesError("INVALID_ARGUMENT", "references must be a list"))
    parsed: list[RepairRef] = []
    for item in raw:
        mapping = _mapping(item)
        if mapping is None:
            return _failure(RepairReferencesError("INVALID_ARGUMENT", "reference entries must be objects"))
        object_name = mapping.get("object")
        if not isinstance(object_name, str) or not object_name.strip():
            return _failure(RepairReferencesError("INVALID_ARGUMENT", "reference object must be a nonempty string"))
        document = mapping.get("document")
        if document is not None and not isinstance(document, str):
            return _failure(RepairReferencesError("INVALID_ARGUMENT", "reference document must be a string"))
        sub_raw = mapping.get("subelements", [])
        subelements: tuple[str, ...]
        if isinstance(sub_raw, str):
            subelements = (sub_raw,) if sub_raw else ()
        elif isinstance(sub_raw, Sequence):
            parts: list[str] = []
            for part in sub_raw:
                if not isinstance(part, str):
                    return _failure(
                        RepairReferencesError("INVALID_ARGUMENT", "subelements must be strings")
                    )
                if part:
                    parts.append(part)
            subelements = tuple(parts)
        else:
            return _failure(RepairReferencesError("INVALID_ARGUMENT", "subelements must be a string or list"))
        parsed.append(
            RepairRef(
                object_name=ObjectName(object_name),
                document_name=document if isinstance(document, str) and document.strip() else None,
                subelements=subelements,
            )
        )
    return tuple(parsed)


def apply_repair_references(doc: object, request: RepairReferencesRequest) -> RepairReferencesReceipt:
    """Repair link properties without recomputing or managing a transaction."""

    repaired: list[tuple[str, str]] = []
    for item in request.repairs:
        owner = get_object(doc, str(item.object_name))
        if owner is None:
            raise RepairReferencesError(
                "OBJECT_NOT_FOUND",
                f"Owner object not found: {item.object_name!r}",
            )
        properties = getattr(owner, "PropertiesList", ())
        if item.property_name not in properties:
            raise RepairReferencesError(
                "PROPERTY_NOT_FOUND",
                f"Object {item.object_name!r} has no property {item.property_name!r}",
            )
        resolved: list[object] = []
        for ref in item.references:
            target = get_object(doc, str(ref.object_name))
            if target is None:
                raise RepairReferencesError(
                    "TARGET_NOT_FOUND",
                    f"Target object not found: {ref.object_name!r}",
                )
            if ref.subelements:
                resolved.append((target, ref.subelements))
            else:
                resolved.append(target)
        getter = getattr(owner, "getTypeIdOfProperty", None)
        prop_type = str(getter(item.property_name)) if callable(getter) else ""
        value: object
        if "LinkSubList" in prop_type:
            value = [
                entry if isinstance(entry, tuple) else (entry, ())
                for entry in resolved
            ]
        elif "LinkList" in prop_type:
            value = [item[0] if isinstance(item, tuple) else item for item in resolved]
        elif "LinkSub" in prop_type:
            if len(resolved) != 1:
                raise RepairReferencesError(
                    "INVALID_ARGUMENT",
                    f"{item.property_name} accepts exactly one reference",
                )
            only = resolved[0]
            value = only if isinstance(only, tuple) else (only, ())
        else:
            if len(resolved) != 1:
                raise RepairReferencesError(
                    "INVALID_ARGUMENT",
                    f"{item.property_name} accepts exactly one reference",
                )
            only = resolved[0]
            if isinstance(only, tuple) and only[1]:
                raise RepairReferencesError(
                    "INVALID_ARGUMENT",
                    f"{item.property_name} does not accept subelements",
                )
            value = only[0] if isinstance(only, tuple) else only
        setattr(owner, item.property_name, value)
        repaired.append((str(item.object_name), item.property_name))
    return RepairReferencesReceipt(
        document_name=document_name(doc), repaired=tuple(repaired)
    )


def read_repair_references_result(
    doc: object, receipt: RepairReferencesReceipt
) -> RepairReferencesInspection:
    """Build the public result after the shared mutation recompute."""

    for object_name, _property_name in receipt.repaired:
        if get_object(doc, object_name) is None:
            raise RepairReferencesError(
                "REPAIRED_OBJECT_MISSING",
                f"Repaired object is missing: {object_name!r}",
            )
    return RepairReferencesInspection(
        document_name=DocumentName(receipt.document_name),
        repaired_count=len(receipt.repaired),
    )


def build_repair_references_request(
    doc_name: object,
    repairs: object,
    recompute: object = False,
    validate: object = False,
) -> RepairReferencesRequest | RepairReferencesFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(
            RepairReferencesError("INVALID_ARGUMENT", "doc_name must be a nonempty string")
        )
    if not isinstance(repairs, Sequence) or isinstance(repairs, (str, bytes)) or not repairs:
        return _failure(
            RepairReferencesError("INVALID_ARGUMENT", "At least one repair is required")
        )
    parsed: list[RepairItem] = []
    for index, raw in enumerate(repairs):
        mapping = _mapping(raw)
        if mapping is None:
            return _failure(
                RepairReferencesError("INVALID_ARGUMENT", f"Repair {index} must be an object")
            )
        object_name = mapping.get("object")
        property_name = mapping.get("property")
        if not isinstance(object_name, str) or not object_name.strip():
            return _failure(
                RepairReferencesError("INVALID_ARGUMENT", f"Repair {index} requires object")
            )
        if not isinstance(property_name, str) or not property_name.strip():
            return _failure(
                RepairReferencesError("INVALID_ARGUMENT", f"Repair {index} requires property")
            )
        refs = _parse_refs(mapping.get("references", []))
        if isinstance(refs, dict):
            return refs
        parsed.append(
            RepairItem(
                object_name=ObjectName(object_name),
                property_name=property_name,
                references=refs,
            )
        )
    recompute_flag = _as_bool(recompute)
    validate_flag = _as_bool(validate)
    if recompute_flag is None or validate_flag is None:
        return _failure(
            RepairReferencesError("INVALID_ARGUMENT", "recompute and validate must be booleans")
        )
    return RepairReferencesRequest(
        doc_name=DocumentName(doc_name),
        repairs=tuple(parsed),
        recompute=recompute_flag,
        validate=validate_flag,
    )


@dataclass(slots=True)
class _RepairReferencesExecution:
    collaborators: RepairReferencesCollaborators
    request: RepairReferencesRequest
    created: RepairReferencesReceipt | None = None
    inspected: RepairReferencesInspection | None = None

    def apply(self, doc: object) -> None:
        self.created = apply_repair_references(doc, self.request)

    def inspect(self, doc: object) -> None:
        if self.created is None:
            raise RepairReferencesError(
                "INVALID_REPAIR_REFERENCES_RESULT",
                "Reference repair did not return an identity receipt",
            )
        self.inspected = read_repair_references_result(doc, self.created)

    def run(self) -> RepairReferencesResult:
        result = run_repair_references_native_mutation(
            self.collaborators,
            str(self.request.doc_name),
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_repair_references_uncertain(
                "REPAIR_REFERENCES_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected repair result",
                committed=True,
            )
        return make_repair_references_success(
            self.inspected.document_name, self.inspected.repaired_count
        )


def run_repair_references(
    collaborators: RepairReferencesCollaborators,
    doc_name: object,
    repairs: object,
    recompute: object = False,
    validate: object = False,
) -> RepairReferencesResult:
    """Run reference repair through apply, recompute, inspection, and commit."""

    request = build_repair_references_request(doc_name, repairs, recompute, validate)
    if isinstance(request, dict):
        return request
    return _RepairReferencesExecution(collaborators, request).run()


class _RepairReferencesRpcFacade(Protocol):
    _cad_collaborators: RepairReferencesCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_repair_references(
    self: _RepairReferencesRpcFacade,
    doc_name: str,
    repairs: object,
    recompute: object = False,
    validate: object = False,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_repair_references(
            collaborators, doc_name, repairs, recompute, validate
        )
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("repair_references", rpc_repair_references)


__all__ = [
    "RepairReferencesCollaborators",
    "RepairReferencesError",
    "RepairReferencesInspection",
    "RepairReferencesReceipt",
    "apply_repair_references",
    "build_repair_references_request",
    "read_repair_references_result",
    "rpc_repair_references",
    "run_repair_references",
    "TYPED_RPC_HANDLER",
]
