"""FreeCADConnection method implementations."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from collections.abc import Iterable, Mapping
from typing import Any

from ...lease_manager import (
    LeaseClientManager,
    LeaseNotFoundError,
    RpcRequestContext,
)
from ...telemetry.context import get_context
from .connection_v2_context_helpers import (
    resolve_document_name_sessions,
    resolve_selector_session,
)

logger = logging.getLogger("FreeCADMCPserver")



def _v2_lease_manager(conn) -> LeaseClientManager | None:
        """Return the connected manager, if authenticated v2 is available."""

        with conn._identity_lock:
            manager = conn._lease_manager
        if manager is None or not manager.connected:
            return None
        return manager


def _build_v2_context(
        conn,
        *,
        document_names: Iterable[str] = (),
        selectors: Iterable[Mapping[str, Any]] = (),
        operation_name: str,
        task_id: str = "",
        request_id: str | None = None,
        require_credentials: bool = True,
    ) -> RpcRequestContext | None:
        """Resolve all declared documents once and freeze one request context.

        ``None`` means the connection has no authenticated v2 manager and the
        caller should use its compatibility RPC route.  Once v2 is connected,
        incomplete or conflicting document scope fails locally instead of
        silently falling back to a credential-less mutation.
        """

        manager = conn._v2_lease_manager()
        if manager is None:
            return None
        with conn._identity_lock:
            resolver = conn._document_session_resolver

        session_ids: list[str] = []

        def add_session(session_uuid: str) -> None:
            if session_uuid and session_uuid not in session_ids:
                session_ids.append(session_uuid)

        resolve_document_name_sessions(resolver, document_names, add_session)
        for raw_selector in selectors:
            resolve_selector_session(manager, resolver, raw_selector, add_session)

        if require_credentials and not session_ids:
            raise LeaseNotFoundError(
                f"authenticated mutation {operation_name!r} has no declared leased document"
            )
        effective_task_id = task_id or get_context().task_id
        return manager.build_request_context(
            document_session_uuids=session_ids,
            operation_name=operation_name,
            task_id=effective_task_id,
            request_id=request_id,
        )


def _unwrap_v2_response(
        conn,
        response: Mapping[str, Any],
        *,
        additional_secrets: Iterable[str] = (),
    ) -> dict[str, Any]:
        """Restore the legacy method-result shape without losing diagnostics."""

        if not isinstance(response, Mapping):
            raise RuntimeError("Invalid invoke_v2 response type")
        result = response.get("result")
        if isinstance(result, Mapping):
            # The inner RPC method owns success/error semantics.  This is also
            # how validation and save failures remain structured when the
            # outer envelope has ``ok=false``.
            unwrapped = dict(result)
            for key in ("request_id", "addon_runtime_id", "leases"):
                if key in response:
                    unwrapped.setdefault(key, response[key])
            # Do not acknowledge acquisition claims here: custody happens in
            # lease_manager.store() after unwrap. Acking early can scrub the
            # vault before the client retains the token.
            with conn._identity_lock:
                manager = conn._lease_manager
            if manager is not None:
                return manager.redact_value(
                    unwrapped, additional_secrets=additional_secrets
                )
            return unwrapped
        error = response.get("error")
        if isinstance(error, Mapping):
            unwrapped = {
                "success": False,
                "error_code": str(error.get("code") or "RPC_V2_ERROR"),
                "error": str(error.get("message") or "Authenticated RPC failed"),
                "request_id": str(response.get("request_id") or ""),
            }
            with conn._identity_lock:
                manager = conn._lease_manager
            if manager is not None:
                return manager.redact_value(
                    unwrapped, additional_secrets=additional_secrets
                )
            return unwrapped
        if response.get("ok") is False:
            return {
                "success": False,
                "error_code": "RPC_V2_ERROR",
                "error": "Authenticated RPC failed without a structured error",
                "request_id": str(response.get("request_id") or ""),
            }
        if result is None:
            return {"success": True}
        raise RuntimeError("Invalid invoke_v2 method result type")


def _invoke_mutation_v2(
        conn,
        method: str,
        params: Mapping[str, Any],
        *,
        document_names: Iterable[str] = (),
        selectors: Iterable[Mapping[str, Any]] = (),
        operation_name: str | None = None,
        task_id: str = "",
        request_id: str | None = None,
        require_credentials: bool = True,
        timeout: float | None = None,
    ) -> dict[str, Any] | None:
        """Invoke an authenticated mutation, or signal compatibility fallback."""

        if request_id is None:
            try:
                from mcp.server.lowlevel.server import request_ctx

                mcp_request_id = str(request_ctx.get().request_id)
            except (ImportError, LookupError, AttributeError):
                mcp_request_id = ""
            if mcp_request_id:
                try:
                    fingerprint_input = json.dumps(
                        {"method": method, "params": dict(params)},
                        ensure_ascii=True,
                        allow_nan=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                except (TypeError, ValueError):
                    fingerprint_input = repr((method, dict(params))).encode(
                        "utf-8", errors="replace"
                    )
                call_fingerprint = hashlib.sha256(fingerprint_input).hexdigest()
                request_id = str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        (
                            f"freecad-mcp:{conn._mcp_instance_id}:"
                            f"{mcp_request_id}:{call_fingerprint}"
                        ),
                    )
                )

        context = conn._build_v2_context(
            document_names=document_names,
            selectors=selectors,
            operation_name=operation_name or method,
            task_id=task_id,
            request_id=request_id,
            require_credentials=require_credentials,
        )
        if context is None:
            return None
        response = conn.invoke_v2(method, params, context, timeout=timeout)
        return conn._unwrap_v2_response(
            response,
            additional_secrets=(
                context.session_token,
                *(item.token for item in context.lease_credentials),
            ),
        )
