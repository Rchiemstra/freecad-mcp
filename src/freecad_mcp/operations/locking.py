"""Document lock / lease operation wrappers."""

from __future__ import annotations

import logging
import os
from typing import Any

from ..freecad_client import FreeCADConnection
from ..lease_manager import LeaseClientManager, LeaseCredential
from ..outcomes import OutcomeStatus
from ..responses import ToolResponse, json_response, tool_fail

logger = logging.getLogger("FreeCADMCPserver")


def _legacy_alias(kind: str, value: Any) -> str:
    raw = str(value or "")
    if not raw:
        return ""
    if kind == "path":
        raw = os.path.normcase(os.path.realpath(os.path.abspath(raw)))
    return f"{kind}:{raw}"


def legacy_selector_doc_key(
    selector: dict[str, Any],
    legacy_document_keys: dict[str, str],
) -> str:
    """Resolve a typed selector to one legacy key, requiring all fields agree."""

    aliases = (
        _legacy_alias("name", selector.get("document_name")),
        _legacy_alias("session", selector.get("document_session_uuid")),
        _legacy_alias("path", selector.get("canonical_path")),
    )
    supplied = tuple(alias for alias in aliases if alias)
    if not supplied or any(
        alias not in legacy_document_keys for alias in supplied
    ):
        return ""
    resolved = {
        legacy_document_keys[alias]
        for alias in supplied
    }
    if len(resolved) > 1:
        return ""
    return next(iter(resolved), "")


def forget_legacy_document_key(
    doc_key: str,
    legacy_document_keys: dict[str, str] | None,
) -> None:
    if legacy_document_keys is None:
        return
    for alias, candidate in list(legacy_document_keys.items()):
        if candidate == doc_key:
            legacy_document_keys.pop(alias, None)


def _lock_response(result: dict[str, Any]) -> ToolResponse:
    if not isinstance(result, dict):
        return tool_fail(f"Unexpected lock response: {result!r}")
    if result.get("success"):
        return json_response(result)
    code = result.get("error_code") or "lock_error"
    message = result.get("error") or code
    return tool_fail(f"[{code}] {message}", structured=result)


def _public_acquisition_result(
    result: dict[str, Any],
    *,
    lease_manager: LeaseClientManager | None,
    credential_stored: bool,
    cleanup_pending: bool = False,
    hide_token: bool = True,
) -> dict[str, Any]:
    public = dict(result)
    if hide_token:
        if lease_manager is not None:
            public = lease_manager.redact_value(public)
        else:
            credential = dict(public.get("credential") or {})
            if credential.get("token"):
                credential["token"] = "[REDACTED]"
                public["credential"] = credential
            elif "credential" in public and not credential:
                public.pop("credential", None)
    public["credential_stored"] = bool(credential_stored)
    public["token_exported"] = False
    if cleanup_pending:
        public["cleanup_pending"] = True
    return public


def _store_lease_grant(
    result: dict[str, Any],
    *,
    lease_manager: LeaseClientManager | None,
    document_sessions: dict[str, str] | None,
    store_token: dict[str, str] | None,
    legacy_document_keys: dict[str, str] | None = None,
    fallback_document_name: str = "",
    freecad: FreeCADConnection | None = None,
) -> dict[str, Any]:
    """Custody a successful acquisition grant into the local lease manager.

    Returns metadata describing custody/acknowledgement outcome so callers can
    surface ``credential_stored=false`` or ``cleanup_pending`` without ever
    exporting the raw token across the model-facing boundary.
    """

    outcome = {
        "credential_stored": False,
        "cleanup_pending": False,
        "stored_new_credential": False,
    }
    credential_data = result.get("credential") or {}
    document_data = result.get("document") or {}
    stored_new_credential = False
    if result.get("success") and credential_data and lease_manager is not None:
        lease_id = str(credential_data["lease_id"])
        document_session_uuid = str(credential_data["document_session_uuid"])
        generation = int(credential_data["generation"])
        token = str(credential_data.get("token") or "")
        credential = None
        if token in {"", "[REDACTED]"}:
            # An idempotent RPC replay can return a cached acquisition result
            # after this process already custodied its one-time token.
            # Response scrubbing then replaces that known secret. Reuse only
            # an exact matching local grant; never infer a missing credential.
            current = lease_manager.get(
                document_session_uuid=document_session_uuid,
            )
            if (
                current is not None
                and current.lease_id == lease_id
                and current.generation == generation
            ):
                credential = current
                outcome["credential_stored"] = True
            else:
                raise ValueError(
                    "redacted acquisition replay has no matching local credential"
                )
        if credential is None:
            credential = LeaseCredential(
                lease_id=lease_id,
                document_session_uuid=document_session_uuid,
                generation=generation,
                token=token,
            )
            stored_new_credential = True
        try:
            canonical_path = document_data.get("canonical_path")
            lease_manager.store(
                credential,
                canonical_paths=([canonical_path] if canonical_path else ()),
            )
        except Exception:
            logger.exception(
                "local acquisition credential custody failed; escrow left unacknowledged"
            )
            outcome["credential_stored"] = False
            return outcome
        outcome["credential_stored"] = True
        outcome["stored_new_credential"] = stored_new_credential
        document_name = str(
            document_data.get("name") or fallback_document_name or ""
        )
        if document_name and document_sessions is not None:
            document_sessions[document_name] = credential.document_session_uuid
        if (
            stored_new_credential
            and freecad is not None
            and result.get("request_id")
            and token not in {"", "[REDACTED]"}
        ):
            try:
                freecad.acknowledge_acquisition_claim(str(result["request_id"]))
            except Exception:
                logger.exception(
                    "acquisition claim acknowledgement after custody failed; "
                    "cleanup pending"
                )
                outcome["cleanup_pending"] = True
    if result.get("success") and store_token is not None:
        lease = result.get("lease") or {}
        token = result.get("token") or lease.get("token")
        doc_key = lease.get("doc_key")
        if token and doc_key:
            store_token[doc_key] = token
            if legacy_document_keys is not None and not credential_data:
                aliases = (
                    _legacy_alias(
                        "name",
                        lease.get("doc_name") or fallback_document_name,
                    ),
                    _legacy_alias(
                        "session", lease.get("document_session_uuid")
                    ),
                    _legacy_alias("path", doc_key if os.path.isabs(doc_key) else ""),
                )
                for alias in aliases:
                    if alias:
                        legacy_document_keys[alias] = str(doc_key)
    return outcome


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


def get_document_lock_operation(
    freecad: FreeCADConnection,
    *,
    doc_name: str = "",
    file_path: str = "",
    session_id: str = "",
    selector: dict[str, Any] | None = None,
) -> ToolResponse:
    try:
        return _lock_response(
            freecad.get_document_lock(
                doc_name=doc_name,
                file_path=file_path,
                session_id=session_id,
                selector=selector,
            )
        )
    except Exception as exc:
        return tool_fail(f"get_document_lock failed: {exc}")


def list_document_locks_operation(freecad: FreeCADConnection) -> ToolResponse:
    try:
        return _lock_response(freecad.list_document_locks())
    except Exception as exc:
        return tool_fail(f"list_document_locks failed: {exc}")


def heartbeat_document_lock_operation(
    freecad: FreeCADConnection,
    *,
    doc_key: str,
    token: str,
    current_operation: str = "",
    state: str = "",
    document_dirty: bool | None = None,
) -> ToolResponse:
    try:
        freecad.set_active_lease_token(token)
        return _lock_response(
            freecad.heartbeat_document_lock(
                doc_key,
                token,
                current_operation=current_operation,
                state=state,
                document_dirty=document_dirty,
            )
        )
    except Exception as exc:
        return tool_fail(f"heartbeat_document_lock failed: {exc}")


def update_document_lock_operation(
    freecad: FreeCADConnection,
    *,
    selector: dict[str, Any],
    task_description: str = "",
    progress_detail: str = "",
) -> ToolResponse:
    try:
        return _lock_response(
            freecad.update_document_lock(
                selector,
                task_description=task_description,
                progress_detail=progress_detail,
            )
        )
    except Exception as exc:
        return tool_fail(f"update_document_lock failed: {exc}")


def release_document_lock_operation(
    freecad: FreeCADConnection,
    *,
    doc_key: str,
    token: str,
    selector: dict[str, Any] | None = None,
    disposition: str = "saved",
    lease_manager: LeaseClientManager | None = None,
    document_sessions: dict[str, str] | None = None,
    store_token: dict[str, str] | None = None,
) -> ToolResponse:
    freecad.set_active_lease_token(token)
    try:
        result = freecad.release_document_lock(
            doc_key,
            token,
            selector=selector,
            disposition=disposition,
        )
        if result.get("success") and selector and lease_manager is not None:
            session_uuid = str(selector.get("document_session_uuid") or "")
            if session_uuid:
                lease_manager.revoke(session_uuid, reason="clean lease release")
                if document_sessions is not None:
                    for name, value in list(document_sessions.items()):
                        if value == session_uuid:
                            document_sessions.pop(name, None)
        if result.get("success") and store_token is not None:
            store_token.pop(doc_key, None)
        return _lock_response(result)
    except Exception as exc:
        return tool_fail(f"release_document_lock failed: {exc}")
    finally:
        freecad.set_active_lease_token(None)


def force_release_stale_lock_operation(
    freecad: FreeCADConnection,
    *,
    doc_key: str,
) -> ToolResponse:
    try:
        return _lock_response(freecad.force_release_stale_lock(doc_key))
    except Exception as exc:
        return tool_fail(f"force_release_stale_lock failed: {exc}")
