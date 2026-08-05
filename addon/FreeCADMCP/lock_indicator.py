"""Persistent, token-safe GUI status for per-document MCP leases.

PySide and FreeCAD are imported lazily so this module remains usable in the
headless test suite.  Closing the detail dock never releases a lease and never
hides the permanent status-bar indicator.
"""

from __future__ import annotations

from typing import Any

# FreeCAD imports this file as ``lock_indicator`` while package callers use
# the qualified spelling.  Publish the first-loaded object under both names
# before importing its collaborators so state and monkeypatch surfaces remain
# a single facade in either environment.
_MODULE_ALIASES = ("addon.FreeCADMCP.lock_indicator", "lock_indicator")

try:
    from addon.FreeCADMCP.lock_indicator_ops.module_aliases import (
        install_facade_aliases as _install_facade_aliases,
    )
    from addon.FreeCADMCP.lock_indicator_ops.module_aliases import (
        install_loaded_module_aliases as _install_loaded_module_aliases,
    )
except ImportError:  # pragma: no cover - flat FreeCAD addon layout
    from lock_indicator_ops.module_aliases import (
        install_facade_aliases as _install_facade_aliases,
    )
    from lock_indicator_ops.module_aliases import (
        install_loaded_module_aliases as _install_loaded_module_aliases,
    )

_install_facade_aliases(__name__, _MODULE_ALIASES)

try:
    from addon.FreeCADMCP.lock_indicator_ops import state
    from addon.FreeCADMCP.lock_indicator_ops.active_leases import (
        _active_leases,
        _foreign_shadow_leases,
    )
    from addon.FreeCADMCP.lock_indicator_ops.constants import (
        _AGENT_OWNED_STATES,
        _LOCAL_SAVE_GUI_TIMEOUT,
        _MUTATING_ACTION_NAMES,
        _MUTATING_ACTION_PREFIXES,
        _SECRET_FIELD_NAMES,
        _mcp_dock_features,
    )
    from addon.FreeCADMCP.lock_indicator_ops.facade_bindings import (
        bind_facade_namespace,
    )
    from addon.FreeCADMCP.lock_indicator_ops.formatting import (
        _bounded_text,
        _format_elapsed,
    )
    from addon.FreeCADMCP.lock_indicator_ops.install import install_lock_indicator
    from addon.FreeCADMCP.lock_indicator_ops.lease_matching import (
        _action_object_name,
        _active_document_hints,
        _active_document_only_hints,
        _agent_owns_active_document,
        _comparison_forms,
        _is_known_mutating_action,
        _lease_canonical_forms,
        _lease_matches_hints,
        _looks_like_canonical_path,
        _looks_like_session_uuid,
        _select_preferred_lease,
        _update_command_deterrence,
    )
    from addon.FreeCADMCP.lock_indicator_ops.lease_presentation import (
        _lease_lines,
        _state_presentation,
    )
    from addon.FreeCADMCP.lock_indicator_ops.lease_view import (
        _credential_owning_mcp_process_alive,
        _is_eligible_exact_owner_stale_timeout,
        _lease_error_code,
        _lease_view,
        _local_hostname,
        _local_recovery_guidance_lines,
        _requires_local_recovery_intervention,
    )
    from addon.FreeCADMCP.lock_indicator_ops.local_recovery import (
        _acknowledge_selected_dirty,
        _confirmed_foreign_takeover,
        _connect_queued_qt_signal,
        _live_document_for_view,
        _local_recovery_capabilities,
        _v2_lease_service,
    )
    from addon.FreeCADMCP.lock_indicator_ops.local_restore import (
        _restore_local_baseline,
        _runtime_restore_components,
        _start_local_baseline_restore_async,
    )
    from addon.FreeCADMCP.lock_indicator_ops.local_restore_gui import (
        _record_public_dict,
    )
    from addon.FreeCADMCP.lock_indicator_ops.local_save import (
        _inspect_local_save_document_gui,
        _runtime_save_components,
        _start_verified_local_save_and_clear_async,
        _submit_local_save_gui,
        _verified_local_save_and_clear,
    )
    from addon.FreeCADMCP.lock_indicator_ops.refresh import (
        _refresh_lock_indicator_now,
        _refresh_set_status_style,
        refresh_lock_indicator,
    )
    from addon.FreeCADMCP.lock_indicator_ops.secret_redaction import (
        _collect_secret_values,
        _redact_secrets,
        _timestamp_age,
    )
except ImportError:
    from lock_indicator_ops import state
    from lock_indicator_ops.active_leases import (  # noqa: F401
        _active_leases,
        _foreign_shadow_leases,
    )
    from lock_indicator_ops.constants import (  # noqa: F401
        _AGENT_OWNED_STATES,
        _LOCAL_SAVE_GUI_TIMEOUT,
        _MUTATING_ACTION_NAMES,
        _MUTATING_ACTION_PREFIXES,
        _SECRET_FIELD_NAMES,
        _mcp_dock_features,
    )
    from lock_indicator_ops.facade_bindings import bind_facade_namespace
    from lock_indicator_ops.formatting import (  # noqa: F401
        _bounded_text,
        _format_elapsed,
    )
    from lock_indicator_ops.install import install_lock_indicator
    from lock_indicator_ops.lease_matching import (  # noqa: F401
        _action_object_name,
        _active_document_hints,
        _active_document_only_hints,
        _agent_owns_active_document,
        _comparison_forms,
        _is_known_mutating_action,
        _lease_canonical_forms,
        _lease_matches_hints,
        _looks_like_canonical_path,
        _looks_like_session_uuid,
        _select_preferred_lease,
        _update_command_deterrence,
    )
    from lock_indicator_ops.lease_presentation import (  # noqa: F401
        _lease_lines,
        _state_presentation,
    )
    from lock_indicator_ops.lease_view import (  # noqa: F401
        _credential_owning_mcp_process_alive,
        _is_eligible_exact_owner_stale_timeout,
        _lease_error_code,
        _lease_view,
        _local_hostname,
        _local_recovery_guidance_lines,
        _requires_local_recovery_intervention,
    )
    from lock_indicator_ops.local_recovery import (  # noqa: F401
        _acknowledge_selected_dirty,
        _confirmed_foreign_takeover,
        _connect_queued_qt_signal,
        _live_document_for_view,
        _local_recovery_capabilities,
        _v2_lease_service,
    )
    from lock_indicator_ops.local_restore import (  # noqa: F401
        _restore_local_baseline,
        _runtime_restore_components,
        _start_local_baseline_restore_async,
    )
    from lock_indicator_ops.local_restore_gui import _record_public_dict  # noqa: F401
    from lock_indicator_ops.local_save import (  # noqa: F401
        _inspect_local_save_document_gui,
        _runtime_save_components,
        _start_verified_local_save_and_clear_async,
        _submit_local_save_gui,
        _verified_local_save_and_clear,
    )
    from lock_indicator_ops.refresh import (  # noqa: F401
        _refresh_lock_indicator_now,
        _refresh_set_status_style,
        refresh_lock_indicator,
    )
    from lock_indicator_ops.secret_redaction import (  # noqa: F401
        _collect_secret_values,
        _redact_secrets,
        _timestamp_age,
    )

_install_loaded_module_aliases()

# §3.3 rename shim — tests may monkeypatch the legacy name.
_set_status_style = _refresh_set_status_style
bind_facade_namespace(globals())

# §3.3 compatibility surfaces — live state is read/written via proxies below.
_STATE_PROXY_NAMES = frozenset(
    {
        "_deterred_actions",
        "_dock_widget",
        "_installed",
        "_refresh_bridge",
        "_refresh_timer",
        "_status_widget",
    }
)

__all__ = [
    "install_lock_indicator",
    "refresh_lock_indicator",
]


def __getattr__(name: str) -> Any:
    if name in _STATE_PROXY_NAMES:
        return getattr(state, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __setattr__(name: str, value: Any) -> None:
    if name in _STATE_PROXY_NAMES:
        setattr(state, name, value)
        return
    globals()[name] = value
