"""MCP tool registration — lease lifecycle (Phase 7 / 7D)."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal

from mcp.server.fastmcp import Context
from mcp.types import CallToolResult

from .operations import (
    force_release_stale_lock_operation,
    forget_legacy_document_key,
    legacy_selector_doc_key,
)
from .responses import json_response, tool_fail
from .tools_server_surfaces import (
    server_connection,
    server_stale_recovery,
    server_state,
)
from .tools_types import DocumentSelectorInput

if TYPE_CHECKING:
    from .freecad_client import FreeCADConnection
    from .instrumented_server import InstrumentedFastMCP
    from .lease_manager import StaleLeaseRecoveryOrchestrator
    from .server_state import ServerState


def _lifecycle_tool_result(result: dict[str, Any]) -> CallToolResult:
    if not result.get("success") and "stale_recovery" not in result:
        session_uuid = str(
            result.get("document_session_uuid")
            or (result.get("aliases") or {}).get("document_session_uuid")
            or ""
        )
        if session_uuid:
            snapshot = server_stale_recovery().recovery_status_snapshot_for(
                (session_uuid,)
            )
            if snapshot.get("sessions"):
                result = {**result, "stale_recovery_health": snapshot}
    if result.get("success"):
        return json_response(result)
    return tool_fail(
        f"[{result.get('error_code', 'document_lifecycle_error')}] "
        f"{result.get('error', 'Document lifecycle operation failed')}",
        structured=result,
    )


def _apply_save_aliases(result: dict[str, Any]) -> None:
    aliases = result.get("aliases") or {}
    session_uuid = str(aliases.get("document_session_uuid") or "")
    new_path = str(aliases.get("canonical_path") or "")
    old_path = str(aliases.get("previous_path") or "")
    if not session_uuid or not new_path:
        return
    lease_manager = server_state().lease_manager
    if old_path and old_path != new_path:
        lease_manager.migrate_alias(
            old_path,
            new_path,
            document_session_uuid=session_uuid,
        )
    elif new_path not in lease_manager.aliases_for(session_uuid):
        lease_manager.add_alias(session_uuid, new_path)


def _register_save_document(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def save_document(
        ctx: Context,
        selector: DocumentSelectorInput,
        validation_profile: str = "default",
    ) -> CallToolResult:
        """Compare, save, hash, reopen-verify, and retain the renewable lease.

        Select the open document with ``document_name``,
        ``document_session_uuid``, or ``canonical_path``. If more than one field is
        supplied, every field must identify the same live document.
        """
        legacy_key = legacy_selector_doc_key(
            dict(selector), server_state().legacy_document_keys
        )
        result = server_connection().save_document(
            selector,
            validation_profile=validation_profile,
            legacy_token=server_state().lease_tokens.get(legacy_key, ""),
        )
        if result.get("success"):
            _apply_save_aliases(result)
        return _lifecycle_tool_result(result)

    exports["save_document"] = save_document


def _register_save_document_as(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def save_document_as(
        ctx: Context,
        selector: DocumentSelectorInput,
        destination: str,
        overwrite: bool = False,
        expected_destination_sha256: str = "",
        validation_profile: str = "default",
    ) -> CallToolResult:
        """Pre-lock, Save As, hash, reopen-verify, and migrate lease aliases.

        Select the open document with ``document_name``,
        ``document_session_uuid``, or ``canonical_path``. If more than one field is
        supplied, every field must identify the same live document.
        """
        result = server_connection().save_document_as(
            selector,
            destination,
            overwrite=overwrite,
            expected_destination_sha256=expected_destination_sha256,
            validation_profile=validation_profile,
        )
        if result.get("success"):
            _apply_save_aliases(result)
        return _lifecycle_tool_result(result)

    exports["save_document_as"] = save_document_as


def _register_finalize_document_edit(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def finalize_document_edit(
        ctx: Context,
        selector: DocumentSelectorInput,
        save_mode: Literal["save", "save_as", "first_save"] = "save",
        destination: str = "",
        overwrite: bool = False,
        expected_destination_sha256: str = "",
        validation_profile: str = "default",
    ) -> CallToolResult:
        """Validate, Save/Save As, reopen-verify, then CAS-release the lease.

        Any validation, save, or sidecar-removal failure retains a visible locked
        error/recovery record instead of presenting a clean release.
        """
        current_state = server_state()
        legacy_key = legacy_selector_doc_key(
            dict(selector), current_state.legacy_document_keys
        )
        result = server_connection().finalize_document_edit(
            selector,
            save_mode=save_mode,
            destination=destination,
            overwrite=overwrite,
            expected_destination_sha256=expected_destination_sha256,
            validation_profile=validation_profile,
            legacy_token=current_state.lease_tokens.get(legacy_key, ""),
        )
        if result.get("success"):
            _apply_save_aliases(result)
            if legacy_key and result.get("released"):
                current_state.lease_tokens.pop(legacy_key, None)
                forget_legacy_document_key(
                    legacy_key, current_state.legacy_document_keys
                )
            session_uuid = str(
                (result.get("aliases") or {}).get("document_session_uuid")
                or selector.get("document_session_uuid")
                or current_state.document_sessions.get(
                    selector.get("document_name", ""), ""
                )
            )
            if session_uuid:
                current_state.lease_manager.revoke(
                    session_uuid, reason="verified finalization completed"
                )
                for name, value in list(current_state.document_sessions.items()):
                    if value == session_uuid:
                        current_state.document_sessions.pop(name, None)
        return _lifecycle_tool_result(result)

    exports["finalize_document_edit"] = finalize_document_edit


def _register_force_release_stale_lock(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    def force_release_stale_lock(ctx: Context, doc_key: str) -> CallToolResult:
        """Deprecated local-only recovery helper; intentionally not MCP-exposed."""
        return force_release_stale_lock_operation(
            server_connection(),
            doc_key=doc_key,
        )

    exports["force_release_stale_lock"] = force_release_stale_lock


def register(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
) -> dict[str, object]:
    """Register lease_lifecycle MCP tools; return exports for §3.3 façade shims."""
    exports: dict[str, object] = {}
    _register_save_document(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_save_document_as(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_finalize_document_edit(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_force_release_stale_lock(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    return exports
