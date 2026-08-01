"""MCP tool registration — lease acquire b (Phase 7 / 7D)."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Literal

from mcp.server.fastmcp import Context
from mcp.types import CallToolResult

from .operations import (
    forget_legacy_document_key,
    heartbeat_document_lock_operation,
    legacy_selector_doc_key,
    release_document_lock_operation,
    update_document_lock_operation,
)
from .responses import tool_fail
from .tools_server_surfaces import server_connection, server_state
from .tools_types import DocumentSelectorInput

if TYPE_CHECKING:
    from .freecad_client import FreeCADConnection
    from .instrumented_server import InstrumentedFastMCP
    from .lease_manager import StaleLeaseRecoveryOrchestrator
    from .server_state import ServerState
def _register_update_document_lock(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def update_document_lock(
        ctx: Context,
        selector: DocumentSelectorInput,
        task_description: str = "",
        progress_detail: str = "",
    ) -> CallToolResult:
        """Update bounded task/progress metadata without changing authority.

        State, heartbeat, dirty status, errors, and mutation revisions remain
        server-owned and cannot be supplied through this tool.
        """
        return update_document_lock_operation(
            server_connection(),
            selector=selector,
            task_description=task_description,
            progress_detail=progress_detail,
        )

    exports['update_document_lock'] = update_document_lock
def _register_release_document_lock(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def release_document_lock(
        ctx: Context,
        selector: DocumentSelectorInput | None = None,
        disposition: Literal["saved", "restored"] = "saved",
        doc_key: str = "",
        token: str = "",
    ) -> CallToolResult:
        """CAS-release only a clean, verified saved/restored document lease.

        Prefer ``selector``; its credential is selected from private MCP memory.
        ``doc_key`` and ``token`` are deprecated protocol-v1 compatibility fields
        for off/observe migration only and are rejected for enforce-mode mutation.
        Agents cannot use this tool for dirty abandonment.
        """
        if selector:
            path_credential = (
                server_state().lease_manager.get(canonical_path=selector["canonical_path"])
                if selector.get("canonical_path")
                else None
            )
            session_candidates = {
                str(value)
                for value in (
                    selector.get("document_session_uuid"),
                    server_state().document_sessions.get(
                        str(selector.get("document_name") or ""), ""
                    ),
                    (
                        path_credential.document_session_uuid
                        if path_credential is not None
                        else ""
                    ),
                )
                if value
            }
            session_uuid = (
                next(iter(session_candidates))
                if len(session_candidates) == 1
                else ""
            )
            credential = (
                server_state().lease_manager.get(document_session_uuid=session_uuid)
                if session_uuid
                else None
            )
            if credential is not None:
                normalized_selector = dict(selector)
                normalized_selector["document_session_uuid"] = session_uuid
                return release_document_lock_operation(
                    server_connection(),
                    doc_key="",
                    token="",
                    selector=normalized_selector,
                    disposition=disposition,
                    lease_manager=server_state().lease_manager,
                    document_sessions=server_state().document_sessions,
                )

            legacy_key = legacy_selector_doc_key(
                dict(selector), server_state().legacy_document_keys
            )
            legacy_token = server_state().lease_tokens.get(legacy_key, "")
            if legacy_key and legacy_token:
                result = release_document_lock_operation(
                    server_connection(),
                    doc_key=legacy_key,
                    token=legacy_token,
                    store_token=server_state().lease_tokens,
                )
                if not result.isError:
                    forget_legacy_document_key(
                        legacy_key, server_state().legacy_document_keys
                    )
                return result
            return tool_fail("Selector does not identify a credential held by this MCP")
        tok = token or server_state().lease_tokens.get(doc_key, "")
        if not tok:
            return tool_fail("No lease token provided and none stored for this doc_key.")
        return release_document_lock_operation(
            server_connection(),
            doc_key=doc_key,
            token=tok,
            store_token=server_state().lease_tokens,
        )

    exports['release_document_lock'] = release_document_lock
def _register_heartbeat_document_lock(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    def heartbeat_document_lock(
        ctx: Context,
        doc_key: str,
        token: str = "",
        current_operation: str = "",
        state_name: str = "",
        document_dirty: bool | None = None,
    ) -> CallToolResult:
        """Deprecated v1 helper; v2 heartbeats are automatic and not MCP-exposed."""
        tok = token or server_state().lease_tokens.get(doc_key, "")
        if not tok:
            return tool_fail(
                "No lease token provided and none stored for this doc_key. "
                "Pass token= from acquire_document_lock."
            )
        return heartbeat_document_lock_operation(
            server_connection(),
            doc_key=doc_key,
            token=tok,
            current_operation=current_operation,
            state=state_name,
            document_dirty=document_dirty,
        )

    exports['heartbeat_document_lock'] = heartbeat_document_lock

def register(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
) -> dict[str, object]:
    """Register lease_acquire_b MCP tools; return exports for §3.3 façade shims."""
    exports: dict[str, object] = {}
    _register_update_document_lock(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_release_document_lock(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_heartbeat_document_lock(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    return exports
