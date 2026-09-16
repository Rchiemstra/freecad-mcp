from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .install_dock_handlers import InstallDockContext
from .lease_matching import _select_preferred_lease
from .lease_presentation import _lease_lines
from .lease_view import _is_eligible_exact_owner_stale_timeout, _lease_view
from .local_recovery import _live_document_for_view, _local_recovery_capabilities, _v2_lease_service
from .secret_redaction import _redact_secrets

try:
    from automation_pause import status as automation_pause_status
except ImportError:  # pragma: no cover - package test layout
    from addon.FreeCADMCP.automation_pause import status as automation_pause_status


def _apply_pause_button(ctx: InstallDockContext) -> str:
    pause = automation_pause_status()
    if pause["paused"]:
        ctx.pause_btn.setText("Resume agent writes")
        ctx.pause_btn.setToolTip(
            "New MCP writes are blocked locally. Click to resume admission."
        )
        if pause["active_write_count"]:
            return "Agent writes are pausing after the current operation."
        return "Agent writes are paused locally."
    ctx.pause_btn.setText("Pause agent writes")
    ctx.pause_btn.setToolTip(
        "Block new MCP writes after any current operation finishes."
    )
    return "Agent writes are currently admitted."


def _apply_capability_buttons(
    ctx: InstallDockContext,
    *,
    capabilities: dict[str, bool],
    view: dict[str, Any],
    local_recovery_busy: bool,
) -> None:
    ctx.takeover_btn.setEnabled(capabilities["takeover"])
    ctx.save_clear_btn.setEnabled(
        capabilities["save_and_clear"] and not local_recovery_busy
    )
    ctx.restore_btn.setEnabled(
        capabilities["restore_baseline"] and not local_recovery_busy
    )
    ctx.keep_dirty_btn.setEnabled(
        capabilities["keep_dirty"] and not local_recovery_busy
    )
    if _is_eligible_exact_owner_stale_timeout(view):
        ctx.takeover_btn.setToolTip(
            "Disabled while the owning MCP runtime automatically recovers "
            "a heartbeat timeout."
        )
    else:
        ctx.takeover_btn.setToolTip(
            (
                "Revokes the selected local or proven-dead imported owner "
                "and increments its fencing generation."
            )
            if capabilities["takeover"]
            else (
                "Takeover requires live selected-document identity and "
                "locally provable owner death."
            )
        )
    ctx.save_clear_btn.setToolTip(
        "Same-path save with hash, archive, matching-worker validation, and CAS release."
        if capabilities["save_and_clear"]
        else "Requires a local taken-over v2 document with a saved baseline."
    )
    ctx.restore_btn.setToolTip(
        "Loads the owner-only lease snapshot in place and preserves the session/lease."
        if capabilities["restore_baseline"]
        else "Requires a local taken-over v2 document with a lease snapshot."
    )
    ctx.keep_dirty_btn.setToolTip(
        "Persists UNLOCKED_DIRTY; new agent acquisitions remain blocked."
        if capabilities["keep_dirty"]
        else "Requires a local taken-over document that FreeCAD reports as dirty."
    )


def build_refresh_from_leases(
    ctx: InstallDockContext,
    *,
    selected_lease: Callable[[], dict[str, Any] | None],
    local_recovery_busy: Callable[[], bool],
) -> Callable[[list[dict[str, Any]]], None]:
    def refresh_from_leases(leases: list[dict[str, Any]]) -> None:
        pause_message = _apply_pause_button(ctx)
        leases = [_redact_secrets(item) for item in leases]
        previous_id = str(ctx.selector.currentData() or "")
        preferred = _select_preferred_lease(leases)
        preferred_id = _lease_view(preferred)["record_id"] if preferred else ""

        records: dict[str, dict[str, Any]] = {}
        ctx.selector.blockSignals(True)
        ctx.selector.clear()
        for lease in leases:
            view = _lease_view(lease)
            record_id = view["record_id"]
            records[record_id] = lease
            ctx.selector.addItem(
                f"{view['filename']} — {view['state']}",
                record_id,
            )
        ctx.dock._mcp_leases_by_id = records  # type: ignore[attr-defined]

        desired_id = previous_id if previous_id in records else preferred_id
        if desired_id:
            index = ctx.selector.findData(desired_id)
            if index >= 0:
                ctx.selector.setCurrentIndex(index)
        ctx.selector.blockSignals(False)
        ctx.selector.setEnabled(bool(leases))

        if not leases:
            ctx.takeover_btn.setEnabled(False)
            ctx.save_clear_btn.setEnabled(False)
            ctx.restore_btn.setEnabled(False)
            ctx.keep_dirty_btn.setEnabled(False)
            ctx.info.setPlainText(f"No active MCP document leases.\n\n{pause_message}")
            return

        selected = selected_lease() or preferred or leases[0]
        selected_view = _lease_view(selected)
        selected_service = _v2_lease_service()
        selected_document = (
            _live_document_for_view(selected_view, selected_service)
            if selected_service is not None and selected_view["is_v2"]
            else None
        )
        capabilities = _local_recovery_capabilities(selected, selected_document)
        _apply_capability_buttons(
            ctx,
            capabilities=capabilities,
            view=selected_view,
            local_recovery_busy=local_recovery_busy(),
        )
        _text, tip = _lease_lines(selected)
        ctx.info.setPlainText(f"{tip}\n\n{pause_message}")

    return refresh_from_leases


def build_refresh_selected_detail(
    ctx: InstallDockContext,
    *,
    selected_lease: Callable[[], dict[str, Any] | None],
    local_recovery_busy: Callable[[], bool],
) -> Callable[[int], None]:
    def refresh_selected_detail(_index: int) -> None:
        pause_message = _apply_pause_button(ctx)
        selected = selected_lease()
        if selected is None:
            return
        _text, tip = _lease_lines(selected)
        ctx.info.setPlainText(f"{tip}\n\n{pause_message}")
        view = _lease_view(selected)
        service = _v2_lease_service()
        document = (
            _live_document_for_view(view, service)
            if service is not None and view["is_v2"]
            else None
        )
        capabilities = _local_recovery_capabilities(selected, document)
        _apply_capability_buttons(
            ctx,
            capabilities=capabilities,
            view=view,
            local_recovery_busy=local_recovery_busy(),
        )

    return refresh_selected_detail
