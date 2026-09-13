"""Versioned, stdlib-only wire contract for ``body_create``."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal, NewType, NotRequired, Protocol, TypedDict, runtime_checkable

BODY_CREATE_CONTRACT_VERSION: Literal[1] = 1

DocumentName = NewType("DocumentName", str)
BodyName = NewType("BodyName", str)


class BodyObject(Protocol):
    """The Body surface inspected before native commit."""

    Name: str
    Label: str
    TypeId: str

    def isDerivedFrom(self, type_name: str) -> bool: ...


class BodyReadDocument(Protocol):
    """Read-only document surface available after native recompute."""

    Name: str

    def getObject(self, name: str) -> BodyObject | None: ...


class BodyDocument(BodyReadDocument, Protocol):
    """Narrow mutation surface available only to the Body apply callback."""

    def addObject(self, object_type: str, name: str) -> BodyObject: ...


@runtime_checkable
class NativeBodyDocument(BodyDocument, Protocol):
    """Runtime-checkable native surface required before Body apply starts."""

    def commitCompatibilityMutation(
        self,
        callback: Callable[[], object],
        *,
        structural: bool = False,
        postcondition: Callable[[], object] | None = None,
    ) -> object: ...


class BodyCreateCollaborators(Protocol):
    """Complete typed boundary between the Body handler and native bridge."""

    def validate_document_invariants(self, document: BodyReadDocument) -> object:
        """Validate the recomputed document before commit."""

        ...

    def commit_body_create_mutation(
        self,
        document_name: DocumentName,
        callback: Callable[[BodyDocument], object],
        postcondition: Callable[[BodyReadDocument], object],
    ) -> object:
        """Run Body creation through its fixed native transaction policy."""

        ...


@dataclass(frozen=True, slots=True, kw_only=True)
class BodyCreateRequest:
    """Validated internal request; the JSON representation remains two strings."""

    doc_name: DocumentName
    body_name: BodyName


class BodyCreateSuccess(TypedDict):
    """Only response shape that may become outward MCP success."""

    contract_version: Literal[1]
    success: Literal[True]
    ok: Literal[True]
    outcome: Literal["committed"]
    committed: Literal[True]
    retry_safe: Literal[False]
    body: BodyName
    label: str


class BodyCreateFailure(TypedDict):
    """A proven rejection or successful rollback."""

    contract_version: Literal[1]
    success: Literal[False]
    ok: Literal[False]
    outcome: Literal["rejected"]
    committed: Literal[False]
    retry_safe: bool
    error_code: str
    error: str
    native_status: NotRequired[str | None]
    native_message: NotRequired[str]
    rollback_succeeded: NotRequired[bool]
    rollback_failed: NotRequired[bool]
    diagnostics: NotRequired[dict[str, object]]


class BodyCreateUncertain(TypedDict):
    """A non-success result whose model state makes automatic retry unsafe."""

    contract_version: Literal[1]
    success: Literal[False]
    ok: Literal[False]
    outcome: Literal["uncertain"]
    committed: bool | None
    retry_safe: Literal[False]
    error_code: str
    error: str
    native_status: NotRequired[str | None]
    native_message: NotRequired[str]
    rollback_succeeded: NotRequired[bool]
    rollback_failed: NotRequired[bool]
    diagnostics: NotRequired[dict[str, object]]


BodyCreateResult = BodyCreateSuccess | BodyCreateFailure | BodyCreateUncertain

_CORE_KEYS = frozenset(
    {
        "contract_version",
        "success",
        "ok",
        "outcome",
        "committed",
        "retry_safe",
        "body",
        "label",
        "error_code",
        "error",
        "native_status",
        "native_message",
        "rollback_succeeded",
        "rollback_failed",
    }
)


def make_body_create_success(body: BodyName, label: str) -> BodyCreateSuccess:
    """Construct a complete committed result using the actual assigned name."""

    return {
        "contract_version": BODY_CREATE_CONTRACT_VERSION,
        "success": True,
        "ok": True,
        "outcome": "committed",
        "committed": True,
        "retry_safe": False,
        "body": body,
        "label": label,
    }


def make_body_create_failure(
    error_code: str,
    error: str,
    *,
    retry_safe: bool = True,
    native_status: str | None = None,
    native_message: str | None = None,
    rollback_succeeded: bool | None = None,
    rollback_failed: bool | None = None,
    diagnostics: dict[str, object] | None = None,
) -> BodyCreateFailure:
    """Construct a proven non-committed result."""

    result: BodyCreateFailure = {
        "contract_version": BODY_CREATE_CONTRACT_VERSION,
        "success": False,
        "ok": False,
        "outcome": "rejected",
        "committed": False,
        "retry_safe": retry_safe,
        "error_code": error_code,
        "error": error,
    }
    if native_status is not None:
        result["native_status"] = native_status
    if native_message is not None:
        result["native_message"] = native_message
    if rollback_succeeded is not None:
        result["rollback_succeeded"] = rollback_succeeded
    if rollback_failed is not None:
        result["rollback_failed"] = rollback_failed
    if diagnostics:
        result["diagnostics"] = diagnostics
    return result


def make_body_create_uncertain(
    error_code: str,
    error: str,
    *,
    committed: bool | None,
    native_status: str | None = None,
    native_message: str | None = None,
    rollback_succeeded: bool | None = None,
    rollback_failed: bool | None = None,
    diagnostics: dict[str, object] | None = None,
) -> BodyCreateUncertain:
    """Construct a result that explicitly forbids automatic replay."""

    result: BodyCreateUncertain = {
        "contract_version": BODY_CREATE_CONTRACT_VERSION,
        "success": False,
        "ok": False,
        "outcome": "uncertain",
        "committed": committed,
        "retry_safe": False,
        "error_code": error_code,
        "error": error,
    }
    if native_status is not None:
        result["native_status"] = native_status
    if native_message is not None:
        result["native_message"] = native_message
    if rollback_succeeded is not None:
        result["rollback_succeeded"] = rollback_succeeded
    if rollback_failed is not None:
        result["rollback_failed"] = rollback_failed
    if diagnostics:
        result["diagnostics"] = diagnostics
    return result


def _diagnostics(response: Mapping[str, object]) -> dict[str, object] | None:
    extra = {str(key): value for key, value in response.items() if key not in _CORE_KEYS}
    return extra or None


def parse_body_create_response(raw_response: object) -> BodyCreateResult:
    """Validate untrusted JSON data without using a type-only ``cast``."""

    if not isinstance(raw_response, Mapping) or not all(
        isinstance(key, str) for key in raw_response
    ):
        return make_body_create_failure(
            "INVALID_RPC_RESPONSE",
            "body_create returned a non-object response",
            retry_safe=False,
        )

    response: dict[str, object] = {}
    for key, value in raw_response.items():
        if not isinstance(key, str):
            return make_body_create_failure(
                "INVALID_RPC_RESPONSE",
                "body_create returned an object with a non-string key",
                retry_safe=False,
            )
        response[key] = value
    diagnostics = _diagnostics(response)
    committed = response.get("committed")
    version = response.get("contract_version")
    success = response.get("success")
    ok = response.get("ok")
    error = response.get("error")
    error_code = response.get("error_code")
    body = response.get("body")
    label = response.get("label")

    valid_success = (
        version == BODY_CREATE_CONTRACT_VERSION
        and success is True
        and ok is True
        and response.get("outcome") == "committed"
        and committed is True
        and response.get("retry_safe") is False
        and isinstance(body, str)
        and bool(body.strip())
        and isinstance(label, str)
        and not error
        and not error_code
    )
    if valid_success:
        assert isinstance(body, str)
        assert isinstance(label, str)
        return make_body_create_success(BodyName(body), label)

    native_status_value = response.get("native_status")
    native_status = native_status_value if isinstance(native_status_value, str) else None
    native_message_value = response.get("native_message")
    native_message = native_message_value if isinstance(native_message_value, str) else None
    rollback_succeeded_value = response.get("rollback_succeeded")
    rollback_succeeded = (
        rollback_succeeded_value if isinstance(rollback_succeeded_value, bool) else None
    )
    rollback_failed_value = response.get("rollback_failed")
    rollback_failed = rollback_failed_value if isinstance(rollback_failed_value, bool) else None

    if committed is True or rollback_succeeded is False or rollback_failed is True:
        return make_body_create_uncertain(
            "BODY_CREATE_COMMITTED_RESPONSE_INVALID"
            if committed is True
            else "BODY_CREATE_ROLLBACK_UNCERTAIN",
            "body_create may have changed the document; automatic retry is unsafe",
            committed=committed if isinstance(committed, bool) else None,
            native_status=native_status,
            native_message=native_message,
            rollback_succeeded=rollback_succeeded,
            rollback_failed=rollback_failed,
            diagnostics=diagnostics,
        )

    declared_failure = (
        version == BODY_CREATE_CONTRACT_VERSION
        and success is False
        and ok is False
        and response.get("outcome") == "rejected"
        and committed is False
        and isinstance(response.get("retry_safe"), bool)
        and isinstance(error_code, str)
        and bool(error_code)
        and isinstance(error, str)
        and bool(error)
    )
    if declared_failure:
        assert isinstance(error_code, str)
        assert isinstance(error, str)
        return make_body_create_failure(
            error_code,
            error,
            retry_safe=response["retry_safe"] is True,
            native_status=native_status,
            native_message=native_message,
            rollback_succeeded=rollback_succeeded,
            rollback_failed=rollback_failed,
            diagnostics=diagnostics,
        )

    preserved_code = error_code if isinstance(error_code, str) and error_code else None
    preserved_error = error if isinstance(error, str) and error else None
    return make_body_create_failure(
        preserved_code or "INVALID_BODY_CREATE_RESPONSE",
        preserved_error or "body_create returned an invalid contract response",
        retry_safe=rollback_succeeded is True,
        native_status=native_status,
        native_message=native_message,
        rollback_succeeded=rollback_succeeded,
        rollback_failed=rollback_failed,
        diagnostics=diagnostics,
    )


__all__ = [
    "BODY_CREATE_CONTRACT_VERSION",
    "BodyCreateCollaborators",
    "BodyCreateFailure",
    "BodyCreateRequest",
    "BodyCreateResult",
    "BodyCreateSuccess",
    "BodyCreateUncertain",
    "BodyDocument",
    "BodyName",
    "BodyObject",
    "BodyReadDocument",
    "DocumentName",
    "make_body_create_failure",
    "make_body_create_success",
    "make_body_create_uncertain",
    "parse_body_create_response",
]
