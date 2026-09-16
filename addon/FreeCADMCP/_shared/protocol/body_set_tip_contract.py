"""Versioned, stdlib-only wire contract for ``body_set_tip``."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal, NewType, NotRequired, Protocol, TypedDict, runtime_checkable

BODY_SET_TIP_CONTRACT_VERSION: Literal[1] = 1

DocumentName = NewType("DocumentName", str)
BodyName = NewType("BodyName", str)
FeatureName = NewType("FeatureName", str)


class TipNamedObject(Protocol):
    """A document object that can be assigned as a Body Tip."""

    @property
    def Name(self) -> str: ...

    @property
    def TypeId(self) -> str: ...

    def isDerivedFrom(self, type_name: str) -> bool: ...


class TipBodyReadObject(Protocol):
    """Read-only Body surface available after native recompute."""

    @property
    def Name(self) -> str: ...

    @property
    def Label(self) -> str: ...

    @property
    def TypeId(self) -> str: ...

    def isDerivedFrom(self, type_name: str) -> bool: ...

    @property
    def Tip(self) -> TipNamedObject | None: ...


class TipBodyWriteObject(Protocol):
    """Body surface available only to the Tip apply callback."""

    @property
    def Name(self) -> str: ...

    @property
    def Label(self) -> str: ...

    @property
    def TypeId(self) -> str: ...

    def isDerivedFrom(self, type_name: str) -> bool: ...

    @property
    def Tip(self) -> TipNamedObject | None: ...

    @Tip.setter
    def Tip(self, feature: TipNamedObject | None) -> None: ...


class TipReadDocument(Protocol):
    """Read-only document surface available after native recompute."""

    @property
    def Name(self) -> str: ...

    def getObject(self, name: str) -> TipBodyReadObject | None: ...


class TipBodyDocument(Protocol):
    """Narrow mutation surface available only to the Tip apply callback."""

    @property
    def Name(self) -> str: ...

    def getObject(self, name: str) -> TipBodyWriteObject | None: ...


@runtime_checkable
class NativeTipDocument(TipBodyDocument, Protocol):
    """Runtime-checkable native surface required before Tip apply starts."""

    def commitCompatibilityMutation(
        self,
        callback: Callable[[], object],
        *,
        structural: bool = False,
        postcondition: Callable[[], object] | None = None,
    ) -> object: ...


class BodySetTipCollaborators(Protocol):
    """Typed boundary between the Tip handler and the generic native bridge."""

    def validate_document_invariants(self, document: TipReadDocument) -> object:
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
        """Run Tip assignment through the generic native transaction policy."""

        ...


@dataclass(frozen=True, slots=True, kw_only=True)
class BodySetTipRequest:
    """Validated internal request; the JSON representation remains three strings."""

    doc_name: DocumentName
    body_name: BodyName
    feature_name: FeatureName


class BodySetTipSuccess(TypedDict):
    """Only response shape that may become outward MCP success."""

    contract_version: Literal[1]
    success: Literal[True]
    ok: Literal[True]
    outcome: Literal["committed"]
    committed: Literal[True]
    retry_safe: Literal[False]
    body: BodyName
    tip: FeatureName
    feature: FeatureName


class BodySetTipFailure(TypedDict):
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


class BodySetTipUncertain(TypedDict):
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


BodySetTipResult = BodySetTipSuccess | BodySetTipFailure | BodySetTipUncertain

_CORE_KEYS = frozenset(
    {
        "contract_version",
        "success",
        "ok",
        "outcome",
        "committed",
        "retry_safe",
        "body",
        "tip",
        "feature",
        "error_code",
        "error",
        "native_status",
        "native_message",
        "rollback_succeeded",
        "rollback_failed",
        "diagnostics",
    }
)


def make_body_set_tip_success(
    body: BodyName, tip: FeatureName, feature: FeatureName
) -> BodySetTipSuccess:
    """Construct a complete committed result using the actual assigned names."""

    return {
        "contract_version": BODY_SET_TIP_CONTRACT_VERSION,
        "success": True,
        "ok": True,
        "outcome": "committed",
        "committed": True,
        "retry_safe": False,
        "body": body,
        "tip": tip,
        "feature": feature,
    }


def make_body_set_tip_failure(
    error_code: str,
    error: str,
    *,
    retry_safe: bool = True,
    native_status: str | None = None,
    native_message: str | None = None,
    rollback_succeeded: bool | None = None,
    rollback_failed: bool | None = None,
    diagnostics: dict[str, object] | None = None,
) -> BodySetTipFailure:
    """Construct a proven non-committed result."""

    result: BodySetTipFailure = {
        "contract_version": BODY_SET_TIP_CONTRACT_VERSION,
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


def make_body_set_tip_uncertain(
    error_code: str,
    error: str,
    *,
    committed: bool | None,
    native_status: str | None = None,
    native_message: str | None = None,
    rollback_succeeded: bool | None = None,
    rollback_failed: bool | None = None,
    diagnostics: dict[str, object] | None = None,
) -> BodySetTipUncertain:
    """Construct a result that explicitly forbids automatic replay."""

    result: BodySetTipUncertain = {
        "contract_version": BODY_SET_TIP_CONTRACT_VERSION,
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
    """Check optional fields too, and preserve extensions without nesting them."""
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


def _invalid_response(response: dict[str, object]) -> BodySetTipUncertain:
    # A malformed response is never evidence of rejection. Preserve a positive
    # commit indication, but don't turn missing or conflicting evidence into False.
    committed = response.get("committed") is True or response.get("native_status") == "Committed"
    rollback_failed = (
        response.get("rollback_failed") is True
        or response.get("rollback_succeeded") is False
        or response.get("native_status") == "RollbackFailed"
    )
    code = (
        "BODY_SET_TIP_COMMITTED_RESPONSE_INVALID"
        if committed
        else "BODY_SET_TIP_ROLLBACK_UNCERTAIN"
        if rollback_failed
        else "INVALID_BODY_SET_TIP_RESPONSE"
    )
    return make_body_set_tip_uncertain(
        code,
        "body_set_tip returned an invalid contract response; document state requires reconciliation",
        committed=True if committed else None,
        diagnostics={"response": response},
    )


def parse_body_set_tip_response(raw_response: object) -> BodySetTipResult:
    """Validate all three wire variants; unknown state always stays uncertain."""
    response = _response_object(raw_response)
    if response is None:
        return make_body_set_tip_uncertain(
            "INVALID_RPC_RESPONSE",
            "body_set_tip returned a non-object response",
            committed=None,
        )
    version = response.get("contract_version")
    details = _response_details(response)
    if type(version) is not int or version != BODY_SET_TIP_CONTRACT_VERSION or details is None:
        return _invalid_response(response)

    body = response.get("body")
    tip = response.get("tip")
    feature = response.get("feature")
    if (
        _valid_success(response)
        and isinstance(body, str)
        and body.strip()
        and isinstance(tip, str)
        and tip.strip()
        and isinstance(feature, str)
        and feature.strip()
    ):
        return make_body_set_tip_success(BodyName(body), FeatureName(tip), FeatureName(feature))

    error_code = response.get("error_code")
    error = response.get("error")
    if (
        response.get("success") is False
        and response.get("ok") is False
        and isinstance(error_code, str)
        and error_code.strip()
        and isinstance(error, str)
        and error.strip()
        and "body" not in response
        and "tip" not in response
        and "feature" not in response
    ):
        if _valid_rejection(response):
            return make_body_set_tip_failure(
                error_code,
                error,
                retry_safe=response["retry_safe"] is True,
                **details,
            )
        if _valid_uncertain(response):
            committed = response["committed"]
            assert committed is None or isinstance(committed, bool)
            return make_body_set_tip_uncertain(error_code, error, committed=committed, **details)
    return _invalid_response(response)


__all__ = [
    "BODY_SET_TIP_CONTRACT_VERSION",
    "BodyName",
    "BodySetTipCollaborators",
    "BodySetTipFailure",
    "BodySetTipRequest",
    "BodySetTipResult",
    "BodySetTipSuccess",
    "BodySetTipUncertain",
    "DocumentName",
    "FeatureName",
    "NativeTipDocument",
    "TipBodyDocument",
    "TipBodyReadObject",
    "TipBodyWriteObject",
    "TipNamedObject",
    "TipReadDocument",
    "make_body_set_tip_failure",
    "make_body_set_tip_success",
    "make_body_set_tip_uncertain",
    "parse_body_set_tip_response",
]
