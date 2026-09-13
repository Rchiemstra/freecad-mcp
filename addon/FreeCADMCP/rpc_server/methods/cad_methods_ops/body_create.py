"""Typed ``body_create`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from .cad_mutation import run_cad_mutation


class BodyCreateCollaborators(Protocol):
    """Narrow dependency contract required by ``run_body_create``."""

    @property
    def freecad(self) -> Any:
        """Provide document lookup through ``getDocument``."""

        ...

    def validate_document_invariants(self, document: Any) -> Any:
        """Validate the recomputed document before commit."""

        ...

    def commit_compatibility_mutation(
        self,
        document_name: str,
        callback: Callable[[], Any],
        *,
        structural: bool = False,
    ) -> Any:
        """Run one mutation through this branch's native transaction boundary."""

        ...


class BodyCreateError(RuntimeError):
    """Failure with a stable RPC-facing error code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class BodyCreateReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    body: Any


def _failure(error: BodyCreateError) -> dict[str, Any]:
    return {
        "success": False,
        "ok": False,
        "error_code": error.code,
        "error": str(error),
    }


def apply_body_create(doc: Any, body_name: str) -> BodyCreateReceipt:
    """Create a Body without recomputing or managing a transaction."""

    if not isinstance(body_name, str):
        raise BodyCreateError("INVALID_ARGUMENT", "body_name must be a string")
    if not body_name.strip():
        raise BodyCreateError("INVALID_ARGUMENT", "body_name must not be empty")
    if doc.getObject(body_name) is not None:
        raise BodyCreateError(
            "OBJECT_ALREADY_EXISTS",
            f"Object already exists: {body_name!r}",
        )

    body = doc.addObject("PartDesign::Body", body_name)
    return BodyCreateReceipt(name=body.Name, body=body)


def _is_partdesign_body(body: Any) -> bool:
    is_derived_from = getattr(body, "isDerivedFrom", None)
    if callable(is_derived_from):
        return bool(is_derived_from("PartDesign::Body"))
    return getattr(body, "TypeId", "") == "PartDesign::Body"


def read_body_result(doc: Any, receipt: BodyCreateReceipt) -> dict[str, Any]:
    """Build the public result after the shared mutation recompute."""

    body = doc.getObject(receipt.name)
    if body is None:
        raise BodyCreateError(
            "CREATED_OBJECT_MISSING",
            f"Created body is missing: {receipt.name!r}",
        )
    if body is not receipt.body:
        raise BodyCreateError(
            "CREATED_OBJECT_REPLACED",
            f"Created body was replaced before commit: {receipt.name!r}",
        )
    if not _is_partdesign_body(body):
        raise BodyCreateError(
            "CREATED_OBJECT_WRONG_TYPE",
            f"Created object is not a PartDesign::Body: {receipt.name!r}",
        )
    return {
        "success": True,
        "ok": True,
        "body": receipt.name,
        "label": getattr(body, "Label", body.Name),
    }


def run_body_create(
    collaborators: BodyCreateCollaborators,
    doc_name: str,
    body_name: str,
) -> dict[str, Any]:
    """Run Body creation through apply, recompute, inspection, and commit."""

    created: dict[str, BodyCreateReceipt] = {}

    def apply(doc: Any) -> dict[str, Any]:
        if doc is None:
            return _failure(
                BodyCreateError(
                    "DOCUMENT_NOT_FOUND",
                    f"Document {doc_name!r} not found",
                )
            )
        try:
            receipt = apply_body_create(doc, body_name)
        except BodyCreateError as exc:
            return _failure(exc)
        except Exception as exc:
            return _failure(BodyCreateError("BODY_CREATE_FAILED", str(exc)))
        created["receipt"] = receipt
        return {"success": True, "ok": True, "body": receipt.name}

    def inspect(doc: Any) -> dict[str, Any]:
        receipt = created.get("receipt")
        if receipt is None:
            return _failure(
                BodyCreateError(
                    "INVALID_BODY_CREATE_RESULT",
                    "Body creation did not return an identity receipt",
                )
            )
        try:
            return read_body_result(doc, receipt)
        except BodyCreateError as exc:
            return _failure(exc)
        except Exception as exc:
            return _failure(BodyCreateError("BODY_CREATE_RESULT_FAILED", str(exc)))

    result = run_cad_mutation(
        collaborators,
        doc_name,
        apply,
        structural=True,
        postcondition=inspect,
        bind_document=True,
    )
    if isinstance(result, dict):
        return result
    return _failure(BodyCreateError("BODY_CREATE_FAILED", str(result)))


__all__ = [
    "BodyCreateCollaborators",
    "BodyCreateError",
    "BodyCreateReceipt",
    "apply_body_create",
    "read_body_result",
    "run_body_create",
]
