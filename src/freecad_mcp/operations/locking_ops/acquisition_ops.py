from __future__ import annotations

import logging
from typing import Any

from ...freecad_client import FreeCADConnection
from ...lease_manager import LeaseClientManager
from ...outcomes import OutcomeStatus
from ...responses import ToolResponse, json_response, tool_fail
from .response_helpers import _lock_response, _public_acquisition_result
from .store_grant import _store_lease_grant

logger = logging.getLogger("FreeCADMCPserver")

def acquire_document_lock_operation(
    freecad: FreeCADConnection,
    *,
    doc_name: str = "",
    file_path: str = "",
    session_id: str = "",
    task_description: str = "",
    client: str = "",
    selector: dict[str, Any] | None = None,
    agent_id: str = "",
    hash_policy: str = "sha256",
    lease_manager: LeaseClientManager | None = None,
    document_sessions: dict[str, str] | None = None,
) -> ToolResponse:
    try:
        result = freecad.acquire_document_lock(
            doc_name=doc_name,
            file_path=file_path,
            session_id=session_id,
            task_description=task_description,
            client=client,
            selector=selector,
            agent_id=agent_id,
            hash_policy=hash_policy,
        )
        if isinstance(result, dict) and result.get("success"):
            custody = _store_lease_grant(
                result,
                lease_manager=lease_manager,
                document_sessions=document_sessions,
                store_token=None,
                fallback_document_name=doc_name,
                freecad=freecad,
            )
            if result.get("credential") and not custody["credential_stored"]:
                public = _public_acquisition_result(
                    result,
                    lease_manager=lease_manager,
                    credential_stored=False,
                )
                public.pop("credential", None)
                return json_response(
                    public,
                    status=OutcomeStatus.WARNING,
                    message=(
                        "Document lock acquired on FreeCAD but local credential "
                        "custody failed; escrow remains unacknowledged for retry"
                    ),
                )
            public = _public_acquisition_result(
                result,
                lease_manager=lease_manager,
                credential_stored=bool(
                    custody["credential_stored"] or not result.get("credential")
                ),
                cleanup_pending=custody["cleanup_pending"],
            )
            if custody["cleanup_pending"]:
                return json_response(
                    public,
                    status=OutcomeStatus.WARNING,
                    message=(
                        "Document lock credential stored locally; escrow cleanup "
                        "is pending"
                    ),
                )
            return _lock_response(public)
        return _lock_response(result)
    except Exception as exc:
        request_id = getattr(exc, "request_id", None)
        logger.error("acquire_document_lock failed: %s", exc)
        if request_id:
            return tool_fail(
                "acquire_document_lock failed: "
                f"{exc}. Use get_request_status / claim_acquisition_result "
                f"with request_id={request_id}"
            )
        return tool_fail(f"acquire_document_lock failed: {exc}")

def adopt_dirty_document_operation(
    freecad: FreeCADConnection,
    *,
    selector: dict[str, Any],
    task_description: str = "",
    client: str = "",
    agent_id: str = "",
    hash_policy: str = "sha256",
    lease_manager: LeaseClientManager | None = None,
    document_sessions: dict[str, str] | None = None,
    store_token: dict[str, str] | None = None,
) -> ToolResponse:
    try:
        result = freecad.adopt_dirty_document(
            selector=selector,
            task_description=task_description,
            client=client,
            agent_id=agent_id,
            hash_policy=hash_policy,
        )
        if (
            isinstance(result, dict)
            and result.get("error_code") == "LOCKED_ERROR_HANDOFF_PENDING"
        ):
            request_id = result.get("request_id")
            message = (
                "Automatic LOCKED_ERROR handoff is still processing. "
                "Poll get_request_status; when result_claimable, call "
                "claim_acquisition_result"
                + (f" with request_id={request_id}" if request_id else "")
                + " to custody the lease. Do not retry adopt until the handoff "
                "completes or is cancelled."
            )
            return json_response(
                {
                    **result,
                    "success": True,
                    "pending": True,
                    "credential_stored": False,
                    "error_code": "LOCKED_ERROR_HANDOFF_PENDING",
                    "error": message,
                    "resume_via": [
                        "get_request_status",
                        "claim_acquisition_result",
                    ],
                },
                status=OutcomeStatus.CONDITION_FALSE,
                message=message,
            )
        if isinstance(result, dict) and result.get("success"):
            custody = _store_lease_grant(
                result,
                lease_manager=lease_manager,
                document_sessions=document_sessions,
                store_token=store_token,
                fallback_document_name=str(selector.get("document_name") or ""),
                freecad=freecad,
            )
            if result.get("credential") and not custody["credential_stored"]:
                public = _public_acquisition_result(
                    result,
                    lease_manager=lease_manager,
                    credential_stored=False,
                )
                public.pop("credential", None)
                return json_response(
                    public,
                    status=OutcomeStatus.WARNING,
                    message=(
                        "Dirty document adopted on FreeCAD but local credential "
                        "custody failed; escrow remains unacknowledged for retry"
                    ),
                )
            public = _public_acquisition_result(
                result,
                lease_manager=lease_manager,
                credential_stored=bool(
                    custody["credential_stored"] or not result.get("credential")
                ),
                cleanup_pending=custody["cleanup_pending"],
            )
            if custody["cleanup_pending"]:
                return json_response(
                    public,
                    status=OutcomeStatus.WARNING,
                    message=(
                        "Adopted credential stored locally; escrow cleanup is pending"
                    ),
                )
            return _lock_response(public)
        return _lock_response(result)
    except Exception as exc:
        request_id = getattr(exc, "request_id", None)
        logger.error("adopt_dirty_document failed: %s", exc)
        if request_id:
            return tool_fail(
                "adopt_dirty_document failed: "
                f"{exc}. Use get_request_status / claim_acquisition_result "
                f"with request_id={request_id}"
            )
        return tool_fail(f"adopt_dirty_document failed: {exc}")

def claim_acquisition_result_operation(
    freecad: FreeCADConnection,
    *,
    request_id: str,
    lease_manager: LeaseClientManager | None = None,
    document_sessions: dict[str, str] | None = None,
    store_token: dict[str, str] | None = None,
) -> ToolResponse:
    """Claim a lost/pending acquisition credential into local MCP custody.

    The raw lease token is retained by this process and never returned to the
    model-facing tool result.
    """

    try:
        result = freecad.claim_acquisition_result(request_id)
        if not isinstance(result, dict) or not result.get("success"):
            code = (
                result.get("error_code") if isinstance(result, dict) else None
            ) or "ACQUISITION_CLAIM_FAILED"
            message = (
                (result.get("error") if isinstance(result, dict) else None)
                or "Acquisition claim failed"
            )
            return tool_fail(
                f"[{code}] {message}",
                structured=result if isinstance(result, dict) else None,
                error_code=str(code),
            )
        if result.get("already_claimed"):
            public = _public_acquisition_result(
                result,
                lease_manager=lease_manager,
                credential_stored=True,
            )
            public.pop("credential", None)
            return json_response(
                public,
                message=(
                    "Acquisition credential was already taken into custody; "
                    "no private token is returned"
                ),
            )
        custody = _store_lease_grant(
            result,
            lease_manager=lease_manager,
            document_sessions=document_sessions,
            store_token=store_token,
            freecad=freecad,
        )
        if result.get("credential") and not custody["credential_stored"]:
            public = _public_acquisition_result(
                result,
                lease_manager=lease_manager,
                credential_stored=False,
            )
            public.pop("credential", None)
            return json_response(
                public,
                status=OutcomeStatus.WARNING,
                message=(
                    "Acquisition claim retrieved but local credential custody "
                    "failed; escrow remains unacknowledged for retry"
                ),
            )
        public = _public_acquisition_result(
            result,
            lease_manager=lease_manager,
            credential_stored=True,
            cleanup_pending=custody["cleanup_pending"],
        )
        public["custodied"] = True
        document = public.get("document") or {}
        document_name = str(document.get("name") or "")
        message = (
            "Acquisition credential claimed and retained by this MCP process"
            + (f" for {document_name}" if document_name else "")
        )
        if custody["cleanup_pending"]:
            message = (
                "Acquisition credential stored locally; escrow cleanup is pending"
                + (f" for {document_name}" if document_name else "")
            )
            return json_response(
                public,
                status=OutcomeStatus.WARNING,
                message=message,
            )
        return json_response(public, message=message)
    except Exception as exc:
        logger.error("claim_acquisition_result failed: %s", exc)
        return tool_fail(f"claim_acquisition_result failed: {exc}")
