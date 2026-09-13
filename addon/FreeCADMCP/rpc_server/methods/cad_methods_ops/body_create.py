"""Typed ``body_create`` mutation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ...._shared.protocol.body_create_contract import (
    BodyCreateCollaborators,
    BodyCreateFailure,
    BodyCreateRequest,
    BodyCreateResult,
    BodyCreateUncertain,
    BodyDocument,
    BodyName,
    BodyObject,
    BodyReadDocument,
    DocumentName,
    make_body_create_failure,
    make_body_create_success,
    make_body_create_uncertain,
    parse_body_create_response,
)
from .cad_mutation import run_body_native_mutation


class BodyCreateError(RuntimeError):
    """Failure with a stable RPC-facing error code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class BodyCreateReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    body: object


@dataclass(frozen=True, slots=True)
class BodyCreateInspection:
    """Read-only data captured after the native-owned recompute."""

    name: BodyName
    label: str


def _failure(error: BodyCreateError, *, retry_safe: bool = True) -> BodyCreateFailure:
    return make_body_create_failure(error.code, str(error), retry_safe=retry_safe)


def apply_body_create(doc: BodyDocument, body_name: BodyName) -> BodyCreateReceipt:
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


def _is_partdesign_body(body: BodyObject) -> bool:
    try:
        return bool(body.isDerivedFrom("PartDesign::Body"))
    except (AttributeError, TypeError):
        return body.TypeId == "PartDesign::Body"


def read_body_result(
    doc: BodyReadDocument, receipt: BodyCreateReceipt
) -> BodyCreateInspection:
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
    return BodyCreateInspection(
        name=BodyName(receipt.name),
        label=str(body.Label),
    )


def build_body_create_request(
    doc_name: object, body_name: object
) -> BodyCreateRequest | BodyCreateFailure:
    """Validate the untyped JSON arguments before constructing internal name types."""

    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(
            BodyCreateError("INVALID_ARGUMENT", "doc_name must be a nonempty string")
        )
    if not isinstance(body_name, str) or not body_name.strip():
        return _failure(
            BodyCreateError("INVALID_ARGUMENT", "body_name must be a nonempty string")
        )
    return BodyCreateRequest(
        doc_name=DocumentName(doc_name),
        body_name=BodyName(body_name),
    )


def _mutation_failure(raw_result: object) -> BodyCreateFailure | BodyCreateUncertain:
    if isinstance(raw_result, Mapping):
        parsed = parse_body_create_response(raw_result)
        if parsed["success"] is False and parsed["error_code"] != "INVALID_BODY_CREATE_RESPONSE":
            return parsed

        native_status_value = raw_result.get("native_status")
        native_status = native_status_value if isinstance(native_status_value, str) else None
        native_message_value = raw_result.get("native_message")
        native_message = native_message_value if isinstance(native_message_value, str) else None
        error_code_value = raw_result.get("error_code")
        error_code = (
            error_code_value
            if isinstance(error_code_value, str) and error_code_value
            else "BODY_CREATE_FAILED"
        )
        error_value = raw_result.get("error")
        error = error_value if isinstance(error_value, str) and error_value else str(raw_result)
        rollback_succeeded_value = raw_result.get("rollback_succeeded")
        rollback_succeeded = (
            rollback_succeeded_value
            if isinstance(rollback_succeeded_value, bool)
            else None
        )
        rollback_failed_value = raw_result.get("rollback_failed")
        rollback_failed = (
            rollback_failed_value if isinstance(rollback_failed_value, bool) else None
        )
        committed_value = raw_result.get("committed")
        committed = committed_value if isinstance(committed_value, bool) else None
        if committed is True or rollback_succeeded is False or rollback_failed is True:
            return make_body_create_uncertain(
                "BODY_CREATE_COMMITTED_RESPONSE_INVALID"
                if committed is True
                else "BODY_CREATE_ROLLBACK_UNCERTAIN",
                error,
                committed=committed,
                native_status=native_status,
                native_message=native_message,
                rollback_succeeded=rollback_succeeded,
                rollback_failed=rollback_failed,
                diagnostics=dict(raw_result),
            )
        return make_body_create_failure(
            error_code,
            error,
            retry_safe=True,
            native_status=native_status,
            native_message=native_message,
            rollback_succeeded=rollback_succeeded,
            rollback_failed=rollback_failed,
            diagnostics=dict(raw_result),
        )
    return _failure(BodyCreateError("BODY_CREATE_FAILED", str(raw_result)))


@dataclass(slots=True)
class _BodyCreateExecution:
    collaborators: BodyCreateCollaborators
    request: BodyCreateRequest
    created: BodyCreateReceipt | None = None
    inspected: BodyCreateInspection | None = None

    def apply(self, doc: BodyDocument) -> object:
        if doc is None:
            return _failure(
                BodyCreateError(
                    "DOCUMENT_NOT_FOUND",
                    f"Document {self.request.doc_name!r} not found",
                )
            )
        try:
            self.created = apply_body_create(doc, self.request.body_name)
        except BodyCreateError as exc:
            return _failure(exc)
        except Exception as exc:
            return _failure(BodyCreateError("BODY_CREATE_FAILED", str(exc)))
        return True

    def inspect(self, doc: BodyReadDocument) -> object:
        if self.created is None:
            return _failure(
                BodyCreateError(
                    "INVALID_BODY_CREATE_RESULT",
                    "Body creation did not return an identity receipt",
                )
            )
        try:
            self.inspected = read_body_result(doc, self.created)
        except BodyCreateError as exc:
            return _failure(exc)
        except Exception as exc:
            return _failure(BodyCreateError("BODY_CREATE_RESULT_FAILED", str(exc)))
        return True

    def run(self) -> BodyCreateResult:
        result = run_body_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is True and self.inspected is not None:
            return make_body_create_success(self.inspected.name, self.inspected.label)
        if result is True:
            return make_body_create_uncertain(
                "BODY_CREATE_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected Body result",
                committed=True,
            )
        return _mutation_failure(result)


def run_body_create(
    collaborators: BodyCreateCollaborators,
    doc_name: object,
    body_name: object,
) -> BodyCreateResult:
    """Run Body creation through apply, recompute, inspection, and commit."""

    request = build_body_create_request(doc_name, body_name)
    if isinstance(request, dict):
        return request
    return _BodyCreateExecution(collaborators, request).run()


__all__ = [
    "BodyCreateCollaborators",
    "BodyCreateError",
    "BodyCreateInspection",
    "BodyCreateReceipt",
    "apply_body_create",
    "build_body_create_request",
    "read_body_result",
    "run_body_create",
]
