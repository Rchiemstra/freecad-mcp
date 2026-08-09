"""RPC bind-host resolution and transport policy."""

from .constants import LEASE_MODE_ENFORCE
from .settings_policy_error import SettingsPolicyError
from .validation import is_loopback_host, validate_settings


def resolve_rpc_bind_host(settings):
    """Resolve the effective bind host and enforce the transport policy."""
    current = validate_settings(settings)
    if not current["remote_enabled"]:
        return "127.0.0.1"
    host = current["rpc_bind_host"]
    if (
        current["document_lease_mode"] == LEASE_MODE_ENFORCE
        and not is_loopback_host(host)
        and not current["allow_authenticated_remote_without_transport_security"]
    ):
        raise SettingsPolicyError(
            "enforce mode refuses a plain non-loopback RPC bind; keep the addon "
            "on loopback behind an SSH/TLS tunnel or explicitly enable the unsafe override"
        )
    return host
