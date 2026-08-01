from __future__ import annotations

import socket
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .facade_bindings import facade_callable
from .secret_redaction import _redact_secrets


def _lease_view(lease: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize legacy and schema-v2 public records for presentation."""

    safe = _redact_secrets(lease)
    document = safe.get("document") if isinstance(safe.get("document"), Mapping) else {}
    local_document = (
        safe.get("local_document")
        if isinstance(safe.get("local_document"), Mapping)
        else {}
    )
    display_document = (
        local_document
        if safe.get("source") == "foreign_recovery" and local_document
        else document
    )
    owner = safe.get("owner") if isinstance(safe.get("owner"), Mapping) else {}
    lease_meta = safe.get("lease") if isinstance(safe.get("lease"), Mapping) else {}
    document_state = (
        safe.get("document_state")
        if isinstance(safe.get("document_state"), Mapping)
        else {}
    )

    canonical_path = display_document.get("canonical_path")
    comparison_key = display_document.get("comparison_key")
    doc_key = (
        safe.get("doc_key")
        or canonical_path
        or display_document.get("session_uuid")
        or safe.get("document_session_uuid")
        or ""
    )
    doc_name = safe.get("doc_name") or display_document.get("name") or ""
    filename = doc_name or doc_key or "(unknown document)"
    if str(doc_key).casefold().endswith(".fcstd"):
        filename = Path(str(doc_key)).name

    state = safe.get("state") or lease_meta.get("state") or "LOCKED_IDLE"
    error = document_state.get("error") or safe.get("error_info")
    baseline = document_state.get("baseline")
    snapshot_id = document_state.get("snapshot_id")
    baseline_available = bool(
        baseline
        or snapshot_id
        or safe.get("baseline_hash")
        or safe.get("baseline_mtime") is not None
    )

    return {
        "record_id": str(
            safe.get("lease_id")
            or display_document.get("session_uuid")
            or safe.get("document_session_uuid")
            or doc_key
        ),
        "is_v2": bool(
            safe.get("schema_version") == 2
            or (isinstance(safe.get("document"), Mapping) and lease_meta)
        ),
        "source": str(safe.get("source") or "local"),
        "lease_id": safe.get("lease_id"),
        "document_session_uuid": (
            display_document.get("session_uuid") or safe.get("document_session_uuid")
        ),
        "canonical_path": str(canonical_path or ""),
        "comparison_key": str(comparison_key or ""),
        "doc_key": str(doc_key),
        "doc_name": str(doc_name),
        "filename": str(filename),
        "state": str(getattr(state, "value", state)),
        "client": owner.get("client") or safe.get("client") or "(unknown)",
        "agent_id": owner.get("agent_id") or safe.get("agent_id") or "",
        "instance_id": owner.get("mcp_instance_id") or safe.get("instance_id") or "",
        "pid": owner.get("mcp_pid") or safe.get("pid"),
        "host": owner.get("hostname") or safe.get("host") or "",
        "mcp_hostname": str(owner.get("mcp_hostname") or ""),
        "current_operation": (
            lease_meta.get("current_operation") or safe.get("current_operation") or ""
        ),
        "task": lease_meta.get("task_summary") or safe.get("task_description") or "",
        "acquired_at": lease_meta.get("acquired_at") or safe.get("acquired_at"),
        "last_heartbeat": (
            lease_meta.get("last_heartbeat_at") or safe.get("last_heartbeat")
        ),
        "dirty": bool(document_state.get("dirty", safe.get("document_dirty", False))),
        "user_intervened": bool(
            document_state.get("user_intervened", safe.get("user_intervened", False))
        ),
        "baseline_available": baseline_available,
        "file_baseline_available": bool(baseline),
        "snapshot_id": str(snapshot_id or ""),
        "error": error if isinstance(error, Mapping) else None,
    }


def _lease_error_code(view: Mapping[str, Any]) -> str:
    error = view.get("error")
    if isinstance(error, Mapping):
        return str(error.get("code") or "").upper()
    return ""


def _local_hostname() -> str:
    try:
        return socket.gethostname()
    except OSError:
        return ""


def _credential_owning_mcp_process_alive(view: Mapping[str, Any]) -> bool:
    """Return True when public owner fields show a co-located MCP process is alive."""

    pid = view.get("pid")
    try:
        pid_value = int(pid)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    if pid_value <= 0:
        return False
    local_host = _local_hostname().casefold()
    if not local_host:
        return False
    owner_host = str(view.get("mcp_hostname") or "").casefold()
    if not owner_host or owner_host != local_host:
        return False
    try:
        from document_lock import pid_alive
    except ImportError:
        from addon.FreeCADMCP.document_lock import pid_alive
    return pid_alive(pid_value)


def _is_eligible_exact_owner_stale_timeout(view: Mapping[str, Any]) -> bool:
    """Return True when STALE is a heartbeat timeout the owning MCP runtime repairs."""

    if str(view.get("state") or "").upper() != "STALE":
        return False
    if view.get("user_intervened"):
        return False
    if view.get("source") not in {"local", ""}:
        return False
    if not view.get("is_v2"):
        return False
    if _lease_error_code(view) != "LEASE_STALE":
        return False
    alive_check = facade_callable(
        "_credential_owning_mcp_process_alive",
        _credential_owning_mcp_process_alive,
    )
    return alive_check(view)


def _requires_local_recovery_intervention(view: Mapping[str, Any]) -> bool:
    """Return True when the operator must use dock recovery, not automatic reconcile."""

    if _is_eligible_exact_owner_stale_timeout(view):
        return False
    state = str(view.get("state") or "").upper()
    source = str(view.get("source") or "local")
    if state in {"USER_INTERVENED", "UNLOCKED_DIRTY", "LOCKED_ERROR"}:
        return True
    if state == "STALE" and view.get("user_intervened"):
        return True
    if state == "STALE" and _lease_error_code(view) == "LEASE_STALE":
        return True
    if source in {"foreign_sidecar", "unknown_sidecar", "foreign_recovery"}:
        return True
    if state == "STALE" and _lease_error_code(view) == "LEASE_OWNER_EXITED":
        return True
    return bool(any(marker in state for marker in ("SIDECAR", "MALFORMED", "FOREIGN")))


def _local_recovery_guidance_lines(view: Mapping[str, Any]) -> list[str]:
    """Return token-free GUI guidance separated by recovery class."""

    if _is_eligible_exact_owner_stale_timeout(view):
        return [
            "Automatic recovery: the owning MCP runtime will reconcile this "
            "heartbeat timeout.",
            "Do not restart FreeCAD, delete the .freecad-mcp.lock sidecar, or "
            "save from the normal GUI.",
            "Unsaved agent work does not need a save first; retry the agent "
            "operation after recovery completes.",
        ]

    if not _requires_local_recovery_intervention(view):
        return []

    state = str(view.get("state") or "").upper()
    source = str(view.get("source") or "local")
    lines = ["Local recovery required:"]
    if source in {"foreign_sidecar", "unknown_sidecar"}:
        lines.append(
            "A foreign or unvalidated sidecar blocks this document. Confirm "
            "the previous owner is dead before takeover."
        )
    elif source == "foreign_recovery":
        lines.append(
            "Imported foreign authority requires confirmed takeover before "
            "local recovery actions."
        )
    elif state == "STALE" and _lease_error_code(view) == "LEASE_OWNER_EXITED":
        lines.append(
            "The recorded MCP owner exited. Use Take over to fence the "
            "document, then save and clear, restore baseline, or acknowledge "
            "dirty state."
        )
    elif state in {"USER_INTERVENED", "UNLOCKED_DIRTY"}:
        lines.append(
            "User intervention rotated ownership. Use the dock recovery "
            "actions below to save and clear, restore baseline, or acknowledge "
            "dirty state."
        )
    elif state == "STALE" and view.get("user_intervened"):
        lines.append(
            "User intervention occurred while the lease was stale. Use the dock "
            "recovery actions below to take over, save and clear, restore "
            "baseline, or acknowledge dirty state."
        )
    elif state == "STALE" and _lease_error_code(view) == "LEASE_STALE":
        lines.append(
            "The recorded MCP owner is not proven alive. Use the dock recovery "
            "actions below to take over, save and clear, restore baseline, or "
            "acknowledge dirty state."
        )
    elif state == "LOCKED_ERROR":
        lines.append(
            "The agent lease is in error. Confirm whether a handoff "
            "continuation is pending before using takeover."
        )
    else:
        lines.append(
            "Use the dock recovery actions below to take over, save and clear, "
            "restore baseline, or acknowledge dirty state."
        )
    lines.append(
        "Preserve the FCStd and sidecar files; do not delete .freecad-mcp.lock "
        "manually."
    )
    return lines
