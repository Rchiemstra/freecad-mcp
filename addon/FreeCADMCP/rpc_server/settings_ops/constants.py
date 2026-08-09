"""Default settings values and lease-mode constants."""

SETTINGS_FILENAME = "freecad_mcp_settings.json"

LEASE_MODE_OFF = "off"
LEASE_MODE_OBSERVE = "observe"
LEASE_MODE_ENFORCE = "enforce"
LEASE_MODES = frozenset({LEASE_MODE_OFF, LEASE_MODE_OBSERVE, LEASE_MODE_ENFORCE})

DEFAULT_SETTINGS = {
    "remote_enabled": False,
    "allowed_ips": "127.0.0.1",
    "auto_start_rpc": False,
    "rpc_port": 9875,
    "rpc_bind_host": "127.0.0.1",
    "freecadcmd_path": "",
    "allow_remote_execute_code": False,
    "instance_id": "",
    "profile_instance_id": "",
    "auth_secret_file": "",
    "document_lease_mode": LEASE_MODE_OBSERVE,
    "allow_network_sidecar": False,
    "persist_task_summary_in_sidecar": False,
    "allow_unsafe_mutating_execute_code": False,
    "allow_authenticated_remote_without_transport_security": False,
    "enable_document_lock": True,
    "document_lock_enforcement": False,
}

# Backwards-compatible private name used by a few out-of-tree addons.
_DEFAULT_SETTINGS = DEFAULT_SETTINGS
