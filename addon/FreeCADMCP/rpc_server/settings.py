"""Persistence and migration for the FreeCAD MCP addon settings.

This module is deliberately the single settings implementation used by both
the workbench commands and the XML-RPC server.  Older releases duplicated the
defaults in ``rpc_server.py`` which made isolated profiles especially easy to
misconfigure.
"""

from __future__ import annotations

import os
import sys

_RPC_SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
if _RPC_SERVER_DIR not in sys.path:
    sys.path.insert(0, _RPC_SERVER_DIR)

try:
    from .settings_ops.bind_host import resolve_rpc_bind_host
    from .settings_ops.constants import (
        _DEFAULT_SETTINGS,
        DEFAULT_SETTINGS,
        LEASE_MODE_ENFORCE,
        LEASE_MODE_OBSERVE,
        LEASE_MODE_OFF,
        LEASE_MODES,
    )
    from .settings_ops.persistence import (
        get_settings_path,
        load_settings,
        save_settings,
    )
    from .settings_ops.profile_secret import ensure_profile_secret
    from .settings_ops.settings_policy_error import SettingsPolicyError
    from .settings_ops.validation import is_loopback_host
except ImportError:
    from settings_ops.bind_host import resolve_rpc_bind_host
    from settings_ops.constants import (
        _DEFAULT_SETTINGS,
        DEFAULT_SETTINGS,
        LEASE_MODE_ENFORCE,
        LEASE_MODE_OBSERVE,
        LEASE_MODE_OFF,
        LEASE_MODES,
    )
    from settings_ops.persistence import (
        get_settings_path,
        load_settings,
        save_settings,
    )
    from settings_ops.profile_secret import ensure_profile_secret
    from settings_ops.settings_policy_error import SettingsPolicyError
    from settings_ops.validation import is_loopback_host

__all__ = [
    "DEFAULT_SETTINGS",
    "LEASE_MODES",
    "LEASE_MODE_ENFORCE",
    "LEASE_MODE_OBSERVE",
    "LEASE_MODE_OFF",
    "_DEFAULT_SETTINGS",
    "SettingsPolicyError",
    "ensure_profile_secret",
    "get_settings_path",
    "is_loopback_host",
    "load_settings",
    "resolve_rpc_bind_host",
    "save_settings",
]
