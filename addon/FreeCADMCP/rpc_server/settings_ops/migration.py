"""Settings migration from legacy lease booleans."""

from .constants import (
    DEFAULT_SETTINGS,
    LEASE_MODE_ENFORCE,
    LEASE_MODE_OBSERVE,
    LEASE_MODE_OFF,
    LEASE_MODES,
)
from .settings_policy_error import SettingsPolicyError


def migrate(settings):
    """Return a migrated copy without silently strengthening old profiles."""
    result = dict(settings) if isinstance(settings, dict) else {}
    if not result.get("rpc_bind_host"):
        result["rpc_bind_host"] = (
            "0.0.0.0" if result.get("remote_enabled", False) else "127.0.0.1"
        )
    has_explicit_mode = "document_lease_mode" in result
    mode = result.get("document_lease_mode")
    if has_explicit_mode and mode not in LEASE_MODES:
        raise SettingsPolicyError(
            "document_lease_mode must be one of: enforce, observe, off"
        )
    if not has_explicit_mode:
        for legacy_key in (
            "enable_document_lock",
            "document_lock_enforcement",
        ):
            if legacy_key in result and not isinstance(result[legacy_key], bool):
                raise SettingsPolicyError(f"{legacy_key} must be true or false")
        enabled = bool(result.get("enable_document_lock", False))
        enforced = bool(result.get("document_lock_enforcement", False))
        if enabled and enforced:
            mode = LEASE_MODE_ENFORCE
        elif enabled:
            mode = LEASE_MODE_OBSERVE
        else:
            mode = LEASE_MODE_OFF
        result["document_lease_mode"] = mode

    result["enable_document_lock"] = mode != LEASE_MODE_OFF
    result["document_lock_enforcement"] = mode == LEASE_MODE_ENFORCE
    if not result.get("profile_instance_id") and result.get("instance_id"):
        result["profile_instance_id"] = result["instance_id"]
    if not result.get("instance_id") and result.get("profile_instance_id"):
        result["instance_id"] = result["profile_instance_id"]
    return result


def with_defaults(settings):
    result = migrate(settings)
    for key, value in DEFAULT_SETTINGS.items():
        result.setdefault(key, value)
    return result
