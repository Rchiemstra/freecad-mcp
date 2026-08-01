from __future__ import annotations

from typing import Any

from ...lease_manager import LeaseClientManager
from ...responses import ToolResponse, json_response, tool_fail


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
