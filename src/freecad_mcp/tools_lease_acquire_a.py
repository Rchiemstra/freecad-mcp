"""Frozen MCP tools for retired document-lease authority."""

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
    def acquire_document_lock(
        ctx: Context,
        doc_name: str = "",
        file_path: str = "",
        session_id: str = "",
        task_description: str = "",
        selector: DocumentSelectorInput | None = None,
        agent_id: str = "",
        hash_policy: Literal["sha256"] = "sha256",
    ) -> CallToolResult:
        """Acquire an exclusive renewable write lease for a FreeCAD document.

        Prefer ``selector`` with an addon-issued ``document_session_uuid`` plus
        optional name/path assertions. All supplied selector fields must resolve to
        the same open document; ActiveDocument is never used. The one-time private
        credential is retained by this MCP process for later calls.

        ``doc_name``, ``file_path``, and ``session_id`` are deprecated selector
        aliases. They still acquire through the authenticated protocol-v2 service
        and produce the same canonical schema-v2 sidecar as ``selector``.
        """

        del ctx, doc_name, file_path, session_id, task_description, selector
        del agent_id, hash_policy
        return _removed()

    @mcp.tool()
    def adopt_dirty_document(
        ctx: Context,
        selector: DocumentSelectorInput,
        task_description: str = "",
        agent_id: str = "",
        hash_policy: Literal["sha256"] = "sha256",
    ) -> CallToolResult:
        """Adopt existing unsaved changes into the verified lease-v2 lifecycle.

        The selector must contain ``document_name``, ``document_session_uuid``, or
        ``canonical_path``. Initial adoption of an unlocked dirty document is
        auto-authorized (no FreeCAD pop-up). Taking over another agent's dirty
        ``LOCKED_ERROR`` lease is also auto-authorized without a FreeCAD pop-up.
        The bounded handoff runs asynchronously while the tool returns a non-error
        ``LOCKED_ERROR_HANDOFF_PENDING`` result with a ``request_id``. Resume with
        ``get_request_status`` then
        ``claim_acquisition_result`` (same path as transport loss).
        ``cancel_request`` aborts the handoff before CAS. Adoption creates a
        recovery snapshot before this MCP process receives the lease credential.
        The main FCStd is not saved by adoption.
        """

        del ctx, selector, task_description, agent_id, hash_policy
        return _removed()

    @mcp.tool()
    def get_document_lock(
        ctx: Context,
        doc_name: str = "",
        file_path: str = "",
        session_id: str = "",
        selector: DocumentSelectorInput | None = None,
    ) -> CallToolResult:
        """Return redacted effective local/foreign lease state for one document.

        Prefer ``selector``. The legacy identity arguments remain temporarily for
        off/observe migration compatibility. Status never includes the bearer token
        or its fingerprint; malformed or conflicting sidecars report locked/unknown.
        """

        del ctx, doc_name, file_path, session_id, selector
        return _removed()

    @mcp.tool()
    def list_document_locks(ctx: Context) -> CallToolResult:
        """List redacted local, foreign, stale, error, and dirty-recovery records.

        The response contains no bearer tokens or token fingerprints.
        """

        del ctx
        return _removed()

    return {
        "acquire_document_lock": acquire_document_lock,
        "adopt_dirty_document": adopt_dirty_document,
        "get_document_lock": get_document_lock,
        "list_document_locks": list_document_locks,
    }
