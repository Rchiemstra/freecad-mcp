from __future__ import annotations

import contextlib

from . import state
from .active_leases import _active_leases
from .document_changes_controls import (
    _native_readiness,
    _requires_immediate_user_attention,
    refresh_document_changes_controls,
)
from .facade_bindings import facade_attr
from .lease_matching import _select_preferred_lease, _update_command_deterrence
from .lease_presentation import _lease_lines, _state_presentation
from .lease_view import _lease_view

try:
    from automation_pause import status as automation_pause_status
except ImportError:  # pragma: no cover - package test layout
    from addon.FreeCADMCP.automation_pause import status as automation_pause_status


def _refresh_set_status_style(state_name: str | None) -> None:
    if state._shared_state.status_widget is None:
        return
    if not state_name:
        color = "#59636e"
    else:
        _icon, color, _label = _state_presentation(state_name)
    state._shared_state.status_widget.setStyleSheet(
        "QLabel#McpDocumentLockStatus {"
        f"color: {color}; font-weight: 600; padding: 1px 5px;"
        "}"
    )


def _refresh_lock_indicator_now() -> None:
    """Refresh widgets.  This private function must run on the Qt GUI thread."""

    leases = _active_leases()
    pause = automation_pause_status()
    core_changes_available = refresh_document_changes_controls()
    if (
        not core_changes_available
        and _requires_immediate_user_attention(_native_readiness())
        and state._shared_state.dock_widget is not None
    ):
        # Older core builds have no Document Changes dock.  Preserve the local
        # MCP Document Lock fallback for rollback/prepared-commit attention.
        state._shared_state.dock_widget.show()
        state._shared_state.dock_widget.raise_()
    _update_command_deterrence(leases)
    if state._shared_state.status_widget is None:
        return
    preferred = _select_preferred_lease(leases)
    if pause["paused"]:
        suffix = "after current operation" if pause["active_write_count"] else ""
        state._shared_state.status_widget.setText(
            "⏸ Agent writes paused" + (f" ({suffix})" if suffix else "")
        )
        state._shared_state.status_widget.setToolTip(
            "A local user paused new MCP writes. Reads remain available."
        )
        state._shared_state.status_widget.setStyleSheet(
            "QLabel#McpDocumentLockStatus {"
            "color: #b7791f; font-weight: 600; padding: 1px 5px;"
            "}"
        )
        state._shared_state.status_widget.setVisible(True)
    elif preferred is None:
        state._shared_state.status_widget.setText("No agent lock")
        state._shared_state.status_widget.setToolTip("No MCP document lease is active")
        _refresh_set_status_style(None)
        state._shared_state.status_widget.setVisible(True)
    else:
        view = _lease_view(preferred)
        text, tip = _lease_lines(preferred)
        icon, _color, _label = _state_presentation(view["state"])
        if len(leases) > 1:
            text += f" (+{len(leases) - 1} more)"
        state._shared_state.status_widget.setText(f"{icon} {text}")
        state._shared_state.status_widget.setToolTip(tip)
        _refresh_set_status_style(view["state"])
        state._shared_state.status_widget.setVisible(True)

    if state._shared_state.dock_widget is not None and hasattr(
        state._shared_state.dock_widget, "refresh_from_leases"
    ):
        state._shared_state.dock_widget.refresh_from_leases(leases)


def refresh_lock_indicator() -> None:
    """Queue a refresh without touching a Qt widget in the calling thread."""

    bridge = facade_attr("_refresh_bridge") or state._shared_state.refresh_bridge
    if bridge is not None:
        with contextlib.suppress(RuntimeError):
            bridge.refresh_requested.emit()
