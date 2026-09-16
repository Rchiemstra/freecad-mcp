"""Versioned, stdlib-only wire contract for ``activate_document``."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal, NewType, NotRequired, Protocol, TypedDict

ACTIVATE_DOCUMENT_CONTRACT_VERSION: Literal[1] = 1

DocumentName = NewType("DocumentName", str)


class ActivateDocumentReadDocument(Protocol):
    """Read-only document surface available after native recompute."""

    @property
    def Name(self) -> str: ...

    def getObject(self, name: str) -> object | None: ...


class ActivateDocumentDocument(ActivateDocumentReadDocument, Protocol):
    """Narrow mutation surface available only to the apply callback."""

    def addObject(self, object_type: str, name: str) -> object: ...


class ActivateDocumentCollaborators(Protocol):
    """Complete typed boundary between the handler and native bridge."""

    def validate_document_invariants(self, document: ActivateDocumentReadDocument) -> object:
        """Validate the recomputed document before commit."""

        ...

    def commit_native_mutation(
        self,
        document_name: str,
        callback: Callable[[object], object],
        postcondition: Callable[[object], object],
        *,
        structural: bool = True,
    ) -> object:
        """Run the mutation through the generic native transaction policy."""

        ...


@dataclass(frozen=True, slots=True, kw_only=True)
class ActivateDocumentRequest:
    """Validated internal request constructed from untyped JSON arguments."""

    doc_name: DocumentName


class ActivateDocumentSuccess(TypedDict):
    """Only response shape that may become outward MCP success."""

    contract_version: Literal[1]
    success: Literal[True]
    ok: Literal[True]
    outcome: Literal["verified"]
    retry_safe: Literal[False]
    document_name: DocumentName
    label: str


class ActivateDocumentFailure(TypedDict):
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




class ActivateDocumentCompensated(TypedDict):
    """A failed operation whose side effects were compensated."""

    contract_version: Literal[1]
    success: Literal[False]
    ok: Literal[False]
    outcome: Literal["compensated"]
    committed: Literal[False]
    retry_safe: Literal[False]
    error_code: str
    error: str
    native_status: NotRequired[str | None]
    native_message: NotRequired[str]
    rollback_succeeded: NotRequired[bool]
    rollback_failed: NotRequired[bool]
    diagnostics: NotRequired[dict[str, object]]

class ActivateDocumentUncertain(TypedDict):
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


ActivateDocumentResult = ActivateDocumentSuccess | ActivateDocumentFailure | ActivateDocumentCompensated | ActivateDocumentUncertain

_CORE_KEYS = frozenset(
    {
        "contract_version",
        "success",
        "ok",
        "outcome",
        "committed",
        "retry_safe",
        "error_code",
        "error",
        "native_status",
        "native_message",
        "rollback_succeeded",
        "rollback_failed",
        "diagnostics",
        "document_name",
        "label",
    }
)


def make_activate_document_success(document_name: DocumentName, label: str) -> ActivateDocumentSuccess:
    """Construct a complete verified result."""

    return {
        "contract_version": ACTIVATE_DOCUMENT_CONTRACT_VERSION,
        "success": True,
        "ok": True,
        "outcome": "verified",
                "retry_safe": False,
        "document_name": document_name,
        "label": label,
    }


def make_activate_document_failure(
    error_code: str,
    error: str,
    *,
    retry_safe: bool = True,
    native_status: str | None = None,
    native_message: str | None = None,
    rollback_succeeded: bool | None = None,
    rollback_failed: bool | None = None,
    diagnostics: dict[str, object] | None = None,
) -> ActivateDocumentFailure:
    """Construct a proven non-committed result."""

    result: ActivateDocumentFailure = {
        "contract_version": ACTIVATE_DOCUMENT_CONTRACT_VERSION,
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




def make_activate_document_compensated(
    error_code: str,
    error: str,
    *,
    native_status: str | None = None,
    native_message: str | None = None,
    rollback_succeeded: bool | None = None,
    rollback_failed: bool | None = None,
    diagnostics: dict[str, object] | None = None,
) -> ActivateDocumentCompensated:
    """Construct a compensated non-success result."""

    result: ActivateDocumentCompensated = {
        "contract_version": ACTIVATE_DOCUMENT_CONTRACT_VERSION,
        "success": False,
        "ok": False,
        "outcome": "compensated",
        "committed": False,
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
def make_activate_document_uncertain(
    error_code: str,
    error: str,
    *,
    committed: bool | None,
    native_status: str | None = None,
    native_message: str | None = None,
    rollback_succeeded: bool | None = None,
    rollback_failed: bool | None = None,
    diagnostics: dict[str, object] | None = None,
) -> ActivateDocumentUncertain:
    """Construct a result that explicitly forbids automatic replay."""

    result: ActivateDocumentUncertain = {
        "contract_version": ACTIVATE_DOCUMENT_CONTRACT_VERSION,
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


def _response_object(raw: object) -> dict[str, object] | None:
    if not isinstance(raw, Mapping):
        return None
    result: dict[str, object] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            return None
        result[key] = value
    return result


class _ResponseDetails(TypedDict, total=False):
    native_status: str | None
    native_message: str
    rollback_succeeded: bool
    rollback_failed: bool
    diagnostics: dict[str, object]


def _read_rollback_flags(response: dict[str, object], details: _ResponseDetails) -> bool:
    for key in ("rollback_succeeded", "rollback_failed"):
        if key in response:
            flag = response[key]
            if not isinstance(flag, bool):
                return False
            if key == "rollback_succeeded":
                details["rollback_succeeded"] = flag
            else:
                details["rollback_failed"] = flag
    return True


def _response_details(response: dict[str, object]) -> _ResponseDetails | None:
    details: _ResponseDetails = {}
    if "native_status" in response:
        status = response["native_status"]
        if status is not None and not isinstance(status, str):
            return None
        details["native_status"] = status
    if "native_message" in response:
        message = response["native_message"]
        if not isinstance(message, str):
            return None
        details["native_message"] = message
    if not _read_rollback_flags(response, details):
        return None
    diagnostics = _response_object(response.get("diagnostics", {}))
    if diagnostics is None:
        return None
    diagnostics.update({key: value for key, value in response.items() if key not in _CORE_KEYS})
    if diagnostics:
        details["diagnostics"] = diagnostics
    return details


def _valid_success(response: dict[str, object]) -> bool:
    return (
        response.get("success") is True
        and response.get("ok") is True
        and response.get("outcome") == "verified"
        and response.get("retry_safe") is False
        and "error" not in response
        and "error_code" not in response
        and "committed" not in response
        and "native_status" not in response
        and "rollback_succeeded" not in response
        and response.get("rollback_failed", False) is False
        and response.get("completion_uncertain", False) is False
    )

def _valid_compensated(response: dict[str, object]) -> bool:
    return (
        response.get("outcome") == "compensated"
        and response.get("committed") is False
        and response.get("retry_safe") is False
    )



def _valid_rejection(response: dict[str, object]) -> bool:
    return (
        response.get("outcome") == "rejected"
        and response.get("committed") is False
        and isinstance(response.get("retry_safe"), bool)
        and response.get("rollback_succeeded", True) is True
        and response.get("rollback_failed", False) is False
        and response.get("native_status") not in {"Committed", "RollbackFailed"}
        and response.get("completion_uncertain", False) is False
    )


def _valid_uncertain(response: dict[str, object]) -> bool:
    return (
        response.get("outcome") == "uncertain"
        and "committed" in response
        and (response["committed"] is None or isinstance(response["committed"], bool))
        and response.get("retry_safe") is False
        and not (response["committed"] is False and response.get("native_status") == "Committed")
        and not (
            response.get("rollback_succeeded") is True
            and response.get("rollback_failed") is True
        )
    )


def _invalid_response(response: dict[str, object]) -> ActivateDocumentUncertain:
    committed = response.get("committed") is True or response.get("native_status") == "Committed"
    rollback_failed = (
        response.get("rollback_failed") is True
        or response.get("rollback_succeeded") is False
        or response.get("native_status") == "RollbackFailed"
    )
    code = (
        "ACTIVATE_DOCUMENT_COMMITTED_RESPONSE_INVALID"
        if committed
        else "ACTIVATE_DOCUMENT_ROLLBACK_UNCERTAIN"
        if rollback_failed
        else "INVALID_ACTIVATE_DOCUMENT_RESPONSE"
    )
    return make_activate_document_uncertain(
        code,
        "activate_document returned an invalid contract response; document state requires reconciliation",
        committed=True if committed else None,
        diagnostics={"response": response},
    )


def parse_activate_document_response(raw_response: object) -> ActivateDocumentResult:
    """Validate all three wire variants; unknown state always stays uncertain."""
    response = _response_object(raw_response)
    if response is None:
        return make_activate_document_uncertain(
            "INVALID_RPC_RESPONSE",
            "activate_document returned a non-object response",
            committed=None,
        )
    version = response.get("contract_version")
    details = _response_details(response)
    if type(version) is not int or version != ACTIVATE_DOCUMENT_CONTRACT_VERSION or details is None:
        return _invalid_response(response)

    document_name = response.get('document_name')
    label = response.get('label')
    if (
        _valid_success(response)
        and isinstance(document_name, str)
        and document_name.strip()
        and isinstance(label, str)
    ):
        return make_activate_document_success(DocumentName(document_name), label)

    error_code = response.get("error_code")
    error = response.get("error")
    if (
        response.get("success") is False
        and response.get("ok") is False
        and isinstance(error_code, str)
        and error_code.strip()
        and isinstance(error, str)
        and error.strip()
        and "document_name" not in response and "label" not in response
    ):
        if _valid_rejection(response):
            return make_activate_document_failure(
                error_code,
                error,
                retry_safe=response["retry_safe"] is True,
                **details,
            )
        if _valid_compensated(response):
            return make_activate_document_compensated(error_code, error, **details)
        if _valid_uncertain(response):
            committed = response["committed"]
            assert committed is None or isinstance(committed, bool)
            return make_activate_document_uncertain(error_code, error, committed=committed, **details)
    return _invalid_response(response)


__all__ = [
    "ACTIVATE_DOCUMENT_CONTRACT_VERSION",
    "ActivateDocumentCollaborators",
    "ActivateDocumentDocument",
    "ActivateDocumentFailure",
    "ActivateDocumentReadDocument",
    "ActivateDocumentRequest",
    "ActivateDocumentResult",
    "ActivateDocumentSuccess",
    "ActivateDocumentUncertain",
    "DocumentName",
    "make_activate_document_compensated",
    "make_activate_document_failure",
    "make_activate_document_success",
    "make_activate_document_uncertain",
    "parse_activate_document_response",
]
