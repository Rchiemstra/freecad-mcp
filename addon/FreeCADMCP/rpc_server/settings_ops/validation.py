"""Security-sensitive settings validation."""

from __future__ import annotations

import ipaddress
import uuid

from .constants import LEASE_MODE_ENFORCE
from .migration import with_defaults
from .settings_policy_error import SettingsPolicyError


def validate_settings(settings):
    """Validate security-sensitive types without coercing truthy strings."""
    result = with_defaults(settings)
    boolean_keys = (
        "remote_enabled",
        "auto_start_rpc",
        "allow_remote_execute_code",
        "allow_network_sidecar",
        "persist_task_summary_in_sidecar",
        "allow_unsafe_mutating_execute_code",
        "allow_authenticated_remote_without_transport_security",
        "enable_document_lock",
        "document_lock_enforcement",
    )
    for key in boolean_keys:
        if not isinstance(result.get(key), bool):
            raise SettingsPolicyError(f"{key} must be true or false")

    port = result.get("rpc_port")
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise SettingsPolicyError("rpc_port must be an integer between 1 and 65535")
    host = result.get("rpc_bind_host")
    if (
        not isinstance(host, str)
        or not host.strip()
        or len(host.strip()) > 255
        or any(ord(character) < 32 for character in host)
    ):
        raise SettingsPolicyError("rpc_bind_host is invalid")
    result["rpc_bind_host"] = host.strip()

    profile_id = result.get("profile_instance_id") or result.get("instance_id")
    if profile_id and not isinstance(profile_id, str):
        raise SettingsPolicyError("profile_instance_id must be a string")
    if result["document_lease_mode"] == LEASE_MODE_ENFORCE and profile_id:
        try:
            uuid.UUID(profile_id)
        except (ValueError, AttributeError) as exc:
            raise SettingsPolicyError(
                "enforce mode profile_instance_id must be a UUID"
            ) from exc
    for key in ("allowed_ips", "freecadcmd_path", "auth_secret_file"):
        if not isinstance(result.get(key), str):
            raise SettingsPolicyError(f"{key} must be a string")
    return result


def fail_closed_settings(message):
    """Return a non-startable policy after malformed persisted configuration."""
    from .constants import DEFAULT_SETTINGS, LEASE_MODE_ENFORCE

    result = dict(DEFAULT_SETTINGS)
    result.update(
        {
            "auto_start_rpc": False,
            "remote_enabled": False,
            "rpc_bind_host": "127.0.0.1",
            "document_lease_mode": LEASE_MODE_ENFORCE,
            "enable_document_lock": True,
            "document_lock_enforcement": True,
            "_configuration_error": str(message)[:512],
        }
    )
    return result


def is_loopback_host(host):
    """Return true only for an unambiguous loopback address/name."""
    if not isinstance(host, str):
        return False
    normalized = host.strip().lower().rstrip(".")
    if normalized == "localhost":
        return True
    if normalized.startswith("[") and normalized.endswith("]"):
        normalized = normalized[1:-1]
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    if address.is_loopback:
        return True
    mapped = getattr(address, "ipv4_mapped", None)
    return bool(mapped is not None and mapped.is_loopback)
