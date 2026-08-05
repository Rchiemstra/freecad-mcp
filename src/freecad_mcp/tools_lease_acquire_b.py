"""Frozen MCP tools for retired lease update/release authority."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Literal

from mcp.server.fastmcp import Context
from mcp.types import CallToolResult

from .responses import tool_fail
from .tools_types import DocumentSelectorInput

if TYPE_CHECKING:
    from .freecad_client import FreeCADConnection
    from .instrumented_server import InstrumentedFastMCP
    from .server_state import ServerState


def _removed() -> CallToolResult:
    result = {
        "success": False,
        "ok": False,
        "error_code": "LEGACY_LEASE_AUTHORITY_REMOVED",
        "error": "Document authority is owned by native FreeCAD collaboration.",
    }
    return tool_fail(
        "[LEGACY_LEASE_AUTHORITY_REMOVED] " + str(result["error"]),
        structured=result,
    )


def register(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: object,
) -> dict[str, object]:
    del state, get_freecad_connection, stale_recovery

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
        del ctx, selector, task_description, progress_detail
        return _removed()

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
        del ctx, selector, disposition, doc_key, token
        return _removed()

    def heartbeat_document_lock(
        ctx: Context,
        doc_key: str,
        token: str = "",
        current_operation: str = "",
        state_name: str = "",
        document_dirty: bool | None = None,
    ) -> CallToolResult:
        del ctx, doc_key, token, current_operation, state_name, document_dirty
        return _removed()

    return {
        "update_document_lock": update_document_lock,
        "release_document_lock": release_document_lock,
        "heartbeat_document_lock": heartbeat_document_lock,
    }
