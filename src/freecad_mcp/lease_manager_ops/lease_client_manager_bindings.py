"""Late-bound method attachments for LeaseClientManager."""

from __future__ import annotations

from .lease_client_credential_ops import (
    add_alias,
    aliases_for,
    close,
    get,
    mark_connected,
    mark_disconnected,
    migrate_alias,
    require,
    revoke,
    store,
)
from .lease_client_heartbeat_ops import (
    apply_heartbeat_response,
    build_heartbeat_envelope,
    build_heartbeat_payload,
    build_heartbeat_request,
    build_request_context,
    credentials_snapshot,
)
from .lease_client_manager_init import init_manager
from .lease_client_status_ops import (
    _build_heartbeat_payload_locked,
    _redact_text_locked,
    _redact_text_with_secrets,
    _require_connected_locked,
    _require_open_locked,
    _secret_snapshot_locked,
    redact_text,
    redact_value,
    redacted_status,
)


def bind_lease_client_manager(LeaseClientManager):
    def _init(self, *args, **kwargs):
        return init_manager(self, *args, **kwargs)

    LeaseClientManager.__init__ = _init

    def _repr(manager):
        with manager._lock:
            return (
                f"{type(manager).__name__}(connected={manager._connected!r}, "
                f"closed={manager._closed!r}, "
                f"credential_count={len(manager._credentials)!r}, "
                f"revocation_count={len(manager._revocations)!r})"
            )

    LeaseClientManager.__repr__ = _repr

    def _connected(manager):
        with manager._lock:
            return manager._connected

    LeaseClientManager.connected = property(_connected)

    LeaseClientManager.mark_connected = mark_connected
    LeaseClientManager.close = close
    LeaseClientManager.mark_disconnected = mark_disconnected
    LeaseClientManager.store = store
    LeaseClientManager.get = get
    LeaseClientManager.require = require
    LeaseClientManager.aliases_for = aliases_for
    LeaseClientManager.add_alias = add_alias
    LeaseClientManager.migrate_alias = migrate_alias
    LeaseClientManager.revoke = revoke
    LeaseClientManager.apply_heartbeat_response = apply_heartbeat_response
    LeaseClientManager.credentials_snapshot = credentials_snapshot
    LeaseClientManager.build_request_context = build_request_context
    LeaseClientManager.build_heartbeat_payload = build_heartbeat_payload
    LeaseClientManager.build_heartbeat_request = build_heartbeat_request
    LeaseClientManager.build_heartbeat_envelope = build_heartbeat_envelope
    LeaseClientManager.redacted_status = redacted_status
    LeaseClientManager._require_connected_locked = _require_connected_locked
    LeaseClientManager._require_open_locked = _require_open_locked
    LeaseClientManager._build_heartbeat_payload_locked = _build_heartbeat_payload_locked
    LeaseClientManager.redact_text = redact_text
    LeaseClientManager.redact_value = redact_value
    LeaseClientManager._secret_snapshot_locked = _secret_snapshot_locked
    LeaseClientManager._redact_text_with_secrets = staticmethod(_redact_text_with_secrets)
    LeaseClientManager._redact_text_locked = _redact_text_locked
