"""Versioned, stdlib-only wire contract for ``preview_attachment``."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal, NewType, NotRequired, Protocol, TypedDict, runtime_checkable

PREVIEW_ATTACHMENT_CONTRACT_VERSION: Literal[1] = 1

DocumentName = NewType("DocumentName", str)
PreviewAttachmentName = NewType("PreviewAttachmentName", str)


class PreviewAttachmentObject(Protocol):
    """Object surface inspected before native commit."""

    @property
    def Name(self) -> str: ...

    @property
    def Label(self) -> str: ...

    @property
    def TypeId(self) -> str: ...


class PreviewAttachmentReadDocument(Protocol):
    """Read-only document surface available after native recompute."""

    @property
    def Name(self) -> str: ...

    def getObject(self, name: str) -> PreviewAttachmentObject | None: ...


class PreviewAttachmentDocument(PreviewAttachmentReadDocument, Protocol):
    """Narrow mutation surface available only to the apply callback."""

    def addObject(self, object_type: str, name: str) -> PreviewAttachmentObject: ...


@runtime_checkable
class NativePreviewAttachmentDocument(PreviewAttachmentDocument, Protocol):
    """Runtime-checkable native surface required before apply starts."""

    def commitCompatibilityMutation(
        self,
        callback: Callable[[], object],
        *,
        structural: bool = False,
        postcondition: Callable[[], object] | None = None,
    ) -> object: ...


class PreviewAttachmentCollaborators(Protocol):
    """Complete typed boundary between the handler and native bridge."""

    def validate_document_invariants(self, document: PreviewAttachmentReadDocument) -> object:
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
        """Run the mutation through the fixed native transaction policy."""

        ...


@dataclass(frozen=True, slots=True, kw_only=True)
class PreviewAttachmentRequest:
    """Validated internal request."""

    doc_name: DocumentName
    datum_name: str


class PreviewAttachmentSuccess(TypedDict):
    """Only response shape that may become outward MCP success."""

    contract_version: Literal[1]
    success: Literal[True]
    ok: Literal[True]
    outcome: Literal["committed"]
    committed: Literal[True]
    retry_safe: Literal[False]
    datum_name: str
    support: NotRequired[object]
    placement: NotRequired[object]
    distance: NotRequired[object]
    normal_angle_deg: NotRequired[object]
    source_body_placement_dropped: NotRequired[bool]
    datum: NotRequired[object]
    datum_body: NotRequired[object]
    support_body: NotRequired[object]
    diff: NotRequired[object]


class PreviewAttachmentFailure(TypedDict):
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


class PreviewAttachmentUncertain(TypedDict):
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


PreviewAttachmentResult = PreviewAttachmentSuccess | PreviewAttachmentFailure | PreviewAttachmentUncertain

_CORE_KEYS = frozenset(
    {
        "contract_version",
        "success",
        "ok",
        "outcome",
        "committed",
        "retry_safe",
        "datum_name",
        "support",
        "placement",
        "distance",
        "normal_angle_deg",
        "source_body_placement_dropped",
        "datum",
        "datum_body",
        "support_body",
        "diff",
        "error_code",
        "error",
        "native_status",
        "native_message",
        "rollback_succeeded",
        "rollback_failed",
        "diagnostics",
    }
)


def make_preview_attachment_success(
    datum_name: str,
    *,
    support: object = None,
    placement: object = None,
    distance: object = None,
    normal_angle_deg: object = None,
    source_body_placement_dropped: object = None,
    datum: object = None,
    datum_body: object = None,
    support_body: object = None,
    diff: object = None,
) -> PreviewAttachmentSuccess:
    """Construct a complete committed result."""

    result: PreviewAttachmentSuccess = {
        "contract_version": PREVIEW_ATTACHMENT_CONTRACT_VERSION,
        "success": True,
        "ok": True,
        "outcome": "committed",
        "committed": True,
        "retry_safe": False,
        "datum_name": datum_name,
    }
    if support is not None:
        result["support"] = support
    if placement is not None:
        result["placement"] = placement
    if distance is not None:
        result["distance"] = distance
    if normal_angle_deg is not None:
        result["normal_angle_deg"] = normal_angle_deg
    if source_body_placement_dropped is not None:
        result["source_body_placement_dropped"] = bool(source_body_placement_dropped)
    if datum is not None:
        result["datum"] = datum
    if datum_body is not None:
        result["datum_body"] = datum_body
    if support_body is not None:
        result["support_body"] = support_body
    if diff is not None:
        result["diff"] = diff
    return result


def make_preview_attachment_failure(
    error_code: str,
    error: str,
    *,
    retry_safe: bool = True,
    native_status: str | None = None,
    native_message: str | None = None,
    rollback_succeeded: bool | None = None,
    rollback_failed: bool | None = None,
    diagnostics: dict[str, object] | None = None,
) -> PreviewAttachmentFailure:
    """Construct a proven non-committed result."""

    result: PreviewAttachmentFailure = {
        "contract_version": PREVIEW_ATTACHMENT_CONTRACT_VERSION,
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


def make_preview_attachment_uncertain(
    error_code: str,
    error: str,
    *,
    committed: bool | None,
    native_status: str | None = None,
    native_message: str | None = None,
    rollback_succeeded: bool | None = None,
    rollback_failed: bool | None = None,
    diagnostics: dict[str, object] | None = None,
) -> PreviewAttachmentUncertain:
    """Construct a result that explicitly forbids automatic replay."""

    result: PreviewAttachmentUncertain = {
        "contract_version": PREVIEW_ATTACHMENT_CONTRACT_VERSION,
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
        and response.get("outcome") == "committed"
        and response.get("committed") is True
        and response.get("retry_safe") is False
        and "error" not in response
        and "error_code" not in response
        and response.get("native_status", "Committed") == "Committed"
        and "rollback_succeeded" not in response
        and response.get("rollback_failed", False) is False
        and response.get("completion_uncertain", False) is False
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


def _invalid_response(response: dict[str, object]) -> PreviewAttachmentUncertain:
    committed = response.get("committed") is True or response.get("native_status") == "Committed"
    rollback_failed = (
        response.get("rollback_failed") is True
        or response.get("rollback_succeeded") is False
        or response.get("native_status") == "RollbackFailed"
    )
    code = (
        "PREVIEW_ATTACHMENT_COMMITTED_RESPONSE_INVALID"
        if committed
        else "PREVIEW_ATTACHMENT_ROLLBACK_UNCERTAIN"
        if rollback_failed
        else "INVALID_PREVIEW_ATTACHMENT_RESPONSE"
    )
    return make_preview_attachment_uncertain(
        code,
        "preview_attachment returned an invalid contract response; document state requires reconciliation",
        committed=True if committed else None,
        diagnostics={"response": response},
    )


def parse_preview_attachment_response(raw_response: object) -> PreviewAttachmentResult:
    """Validate all three wire variants; unknown state always stays uncertain."""
    response = _response_object(raw_response)
    if response is None:
        return make_preview_attachment_uncertain(
            "INVALID_RPC_RESPONSE",
            "preview_attachment returned a non-object response",
            committed=None,
        )
    version = response.get("contract_version")
    details = _response_details(response)
    if type(version) is not int or version != PREVIEW_ATTACHMENT_CONTRACT_VERSION or details is None:
        return _invalid_response(response)

    datum_name = response.get('datum_name')
    if (
        _valid_success(response)
        and isinstance(datum_name, str) and datum_name.strip()
    ):
        return make_preview_attachment_success(
            str(datum_name),
            support=response.get("support"),
            placement=response.get("placement"),
            distance=response.get("distance"),
            normal_angle_deg=response.get("normal_angle_deg"),
            source_body_placement_dropped=response.get("source_body_placement_dropped"),
            datum=response.get("datum"),
            datum_body=response.get("datum_body"),
            support_body=response.get("support_body"),
            diff=response.get("diff"),
        )

    error_code = response.get("error_code")
    error = response.get("error")
    if (
        response.get("success") is False
        and response.get("ok") is False
        and isinstance(error_code, str)
        and error_code.strip()
        and isinstance(error, str)
        and error.strip()
        and 'datum_name' not in response
    ):
        if _valid_rejection(response):
            return make_preview_attachment_failure(
                error_code,
                error,
                retry_safe=response["retry_safe"] is True,
                **details,
            )
        if _valid_uncertain(response):
            committed = response["committed"]
            assert committed is None or isinstance(committed, bool)
            return make_preview_attachment_uncertain(error_code, error, committed=committed, **details)
    return _invalid_response(response)


__all__ = [
    "PREVIEW_ATTACHMENT_CONTRACT_VERSION",
    "PreviewAttachmentCollaborators",
    "PreviewAttachmentFailure",
    "PreviewAttachmentRequest",
    "PreviewAttachmentResult",
    "PreviewAttachmentSuccess",
    "PreviewAttachmentUncertain",
    "PreviewAttachmentDocument",
    "PreviewAttachmentName",
    "PreviewAttachmentObject",
    "PreviewAttachmentReadDocument",
    "DocumentName",
    "make_preview_attachment_failure",
    "make_preview_attachment_success",
    "make_preview_attachment_uncertain",
    "parse_preview_attachment_response",
]
