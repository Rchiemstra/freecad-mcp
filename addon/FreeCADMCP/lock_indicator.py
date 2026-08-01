"""Persistent, token-safe GUI status for per-document MCP leases.

PySide and FreeCAD are imported lazily so this module remains usable in the
headless test suite.  Closing the detail dock never releases a lease and never
hides the permanent status-bar indicator.
"""

from __future__ import annotations

import sys
from typing import Any

# FreeCAD adds this addon directory directly to ``sys.path`` and imports this
# file as ``lock_indicator``.  Package-aware callers (including the test suite)
# import the same file as ``addon.FreeCADMCP.lock_indicator``.  Without an early
# alias Python executes the file twice, producing two state modules, two
# install routines, and two refresh bridges.  Whichever name loads first owns
# the single module object; publishing both names here makes every later import
# resolve to that same object in either environment.
_CANONICAL_MODULE_NAME = "addon.FreeCADMCP.lock_indicator"
_FREECAD_MODULE_NAME = "lock_indicator"
_MODULE_ALIASES = (_CANONICAL_MODULE_NAME, _FREECAD_MODULE_NAME)


def _install_module_aliases() -> None:
    current = sys.modules.get(__name__)
    if current is None:  # pragma: no cover - import machinery always sets it
        return

    owner = next(
        (
            module
            for alias in _MODULE_ALIASES
            if (module := sys.modules.get(alias)) is not None
            and module is not current
        ),
        current,
    )
    for alias in _MODULE_ALIASES:
        sys.modules[alias] = owner


_install_module_aliases()

try:
    from .lock_indicator_ops.module_aliases import install_module_aliases, install_package_aliases
except ImportError:
    from lock_indicator_ops.module_aliases import install_module_aliases, install_package_aliases

try:
    from .lock_indicator_ops import state
    from .lock_indicator_ops.active_leases import (
        _active_leases,
        _foreign_shadow_leases,
    )
    from .lock_indicator_ops.constants import (
        _AGENT_OWNED_STATES,
        _LOCAL_SAVE_GUI_TIMEOUT,
        _MUTATING_ACTION_NAMES,
        _MUTATING_ACTION_PREFIXES,
        _SECRET_FIELD_NAMES,
        _mcp_dock_features,
    )
    from .lock_indicator_ops.formatting import _bounded_text, _format_elapsed
    from .lock_indicator_ops.install import install_lock_indicator
    from .lock_indicator_ops.lease_matching import (
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
    from .lock_indicator_ops.lease_presentation import (
        _lease_lines,
        _state_presentation,
    )
    from .lock_indicator_ops.lease_view import (
        _credential_owning_mcp_process_alive,
        _is_eligible_exact_owner_stale_timeout,
        _lease_error_code,
        _lease_view,
        _local_hostname,
        _local_recovery_guidance_lines,
        _requires_local_recovery_intervention,
    )
    from .lock_indicator_ops.local_recovery import (
        _acknowledge_selected_dirty,
        _confirmed_foreign_takeover,
        _connect_queued_qt_signal,
        _live_document_for_view,
        _local_recovery_capabilities,
        _v2_lease_service,
    )
    from .lock_indicator_ops.local_restore import (
        _restore_local_baseline,
        _runtime_restore_components,
        _start_local_baseline_restore_async,
    )
    from .lock_indicator_ops.local_restore_gui import _record_public_dict
    from .lock_indicator_ops.local_save import (
        _inspect_local_save_document_gui,
        _runtime_save_components,
        _start_verified_local_save_and_clear_async,
        _submit_local_save_gui,
        _verified_local_save_and_clear,
    )
    from .lock_indicator_ops.refresh import (
        _refresh_lock_indicator_now,
        _refresh_set_status_style,
        refresh_lock_indicator,
    )
    from .lock_indicator_ops.secret_redaction import (
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
    from lock_indicator_ops.formatting import _bounded_text, _format_elapsed  # noqa: F401
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

install_package_aliases()

for _mod_name in list(sys.modules):
    if _mod_name.startswith("lock_indicator_ops.") or _mod_name.startswith(
        "addon.FreeCADMCP.lock_indicator_ops."
    ):
        install_module_aliases(_mod_name)

# §3.3 rename shim — tests may monkeypatch the legacy name.
_set_status_style = _refresh_set_status_style

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
