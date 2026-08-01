from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .formatting import _bounded_text, _format_elapsed
from .lease_view import (
    _is_eligible_exact_owner_stale_timeout,
    _lease_view,
    _local_recovery_guidance_lines,
    _requires_local_recovery_intervention,
)
from .secret_redaction import _timestamp_age


def _state_presentation(state: str) -> tuple[str, str, str]:
    """Return ``(icon, color, human label)`` for every v2 state family."""

    normalized = str(state or "").upper()
    if normalized in {"LOCKED_SAVING", "RELEASING"}:
        return (
            "◆",
            "#7b3fb5",
            {
                "LOCKED_SAVING": "Saving / verifying",
                "RELEASING": "Finalizing",
            }[normalized],
        )
    if normalized in {"ACQUIRING", "CANCELLING", "STALE"}:
        return (
            "⌛",
            "#a15c00",
            {
                "ACQUIRING": "Preparing lease",
                "CANCELLING": "Cancelling",
                "STALE": "Stale lease",
            }[normalized],
        )
    if normalized in {
        "LOCKED_ERROR",
        "USER_INTERVENED",
        "UNLOCKED_DIRTY",
    }:
        return (
            "⚠",
            "#b42318",
            {
                "LOCKED_ERROR": "Lease error",
                "USER_INTERVENED": "User intervened",
                "UNLOCKED_DIRTY": "Unlocked with unsaved changes",
            }[normalized],
        )
    if any(
        marker in normalized
        for marker in ("ERROR", "INTERVENED", "DIRTY", "MISSING", "MALFORMED")
    ):
        return "⚠", "#b42318", "Lease coordination error"
    if "NETWORK" in normalized or "LOWER_ASSURANCE" in normalized:
        return "⌛", "#a15c00", "Lower-assurance lease"
    if normalized == "UNLOCKED_SAVED":
        return "✓", "#287a3d", "Saved and unlocked"
    return (
        "🔒",
        "#2764c5",
        {
            "LOCKED_EDITING": "Agent editing",
            "LOCKED_RECOMPUTING": "Agent recomputing",
            "LOCKED_IDLE": "Agent lease idle",
        }.get(normalized, "Agent lease"),
    )


def _lease_lines(lease: Mapping[str, Any]) -> tuple[str, str]:
    """Return token-safe ``(status_bar_text, tooltip)``."""

    view = _lease_view(lease)
    _icon, _color, state_label = _state_presentation(view["state"])
    if _is_eligible_exact_owner_stale_timeout(view):
        state_label = "Stale lease (auto-recovering)"
    elif (
        view["state"].upper() == "STALE"
        and _requires_local_recovery_intervention(view)
    ):
        state_label = "Stale lease (recovery required)"
    operation = _bounded_text(view["current_operation"])
    text = f"{state_label} {view['filename']}"
    if operation:
        text += f" — {operation}"
    if view["dirty"]:
        text += " — Unsaved"

    owner_label = _bounded_text(view["agent_id"] or view["client"])
    acquired_age = _timestamp_age(view["acquired_at"])
    heartbeat_age = _timestamp_age(view["last_heartbeat"])
    tip_lines = [
        f"Document: {_bounded_text(view['filename'], limit=260)}",
        f"Document name: {_bounded_text(view['doc_name']) or '(unknown)'}",
        f"State: {_bounded_text(view['state'])}",
        f"Source: {_bounded_text(view['source']).replace('_', ' ')}",
        f"Agent/client: {owner_label or '(unknown)'}",
        f"MCP instance: {_bounded_text(view['instance_id']) or '(unknown)'}",
        "PID: "
        f"{view['pid'] or '(unknown)'}  "
        f"host: {_bounded_text(view['host']) or '(unknown)'}",
        f"Operation: {operation or '(idle)'}",
        f"Task: {_bounded_text(view['task']) or '(none)'}",
        f"Held for: {_format_elapsed(acquired_age)}",
        f"Last heartbeat: {_format_elapsed(heartbeat_age)} ago",
        f"Unsaved: {'yes' if view['dirty'] else 'no'}",
        "Recovery baseline: "
        f"{'available' if view['baseline_available'] else 'not available'}",
    ]
    if view["error"]:
        tip_lines.append(
            "Error: "
            + _bounded_text(
                view["error"].get("code") or view["error"].get("message") or "unknown"
            )
        )
    guidance = _local_recovery_guidance_lines(view)
    if guidance:
        tip_lines.append("")
        tip_lines.extend(guidance)
    return text, "\n".join(tip_lines)
