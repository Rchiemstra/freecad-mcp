"""Frozen compatibility adapter for the removed MCP lease client authority."""

from __future__ import annotations

__all__ = ("LeaseClientManager", "bind_lease_client_manager")


def _legacy_lease_authority_removed() -> dict[str, object]:
    """Return a fresh, deterministic result for the removed authority."""

    return {
        "success": False,
        "ok": False,
        "error_code": "LEGACY_LEASE_AUTHORITY_REMOVED",
        "error": "Document authority is owned by native FreeCAD collaboration.",
    }


def LeaseClientManager(*args, **kwargs) -> dict[str, object]:
    """Retain the historic constructor surface as a deprecation callable."""

    del args, kwargs
    return _legacy_lease_authority_removed()


def bind_lease_client_manager(LeaseClientManager) -> None:
    """Retain the historic no-op binder import during compatibility removal."""

    del LeaseClientManager


def _compat_init_manager(manager, *, session_token=None) -> None:
    """Retain the retired initializer without storing authority state."""

    del manager, session_token


def _compat_mark_connected(manager, session_token):
    del manager, session_token
    return _legacy_lease_authority_removed()


def _compat_close(manager, reason="MCP process shutdown"):
    del manager, reason
    return _legacy_lease_authority_removed()


def _compat_mark_disconnected(manager, reason="connection closed"):
    del manager, reason
    return _legacy_lease_authority_removed()


def _compat_store(manager, credential, *, canonical_paths=(), replace=False):
    del manager, credential, canonical_paths, replace
    return _legacy_lease_authority_removed()


def _compat_get(
    manager,
    *,
    document_session_uuid=None,
    canonical_path=None,
):
    del manager, document_session_uuid, canonical_path
    return _legacy_lease_authority_removed()


def _compat_require(
    manager,
    *,
    document_session_uuid=None,
    canonical_path=None,
):
    del manager, document_session_uuid, canonical_path
    return _legacy_lease_authority_removed()


def _compat_aliases_for(manager, document_session_uuid):
    del manager, document_session_uuid
    return _legacy_lease_authority_removed()


def _compat_add_alias(manager, document_session_uuid, canonical_path):
    del manager, document_session_uuid, canonical_path
    return _legacy_lease_authority_removed()


def _compat_migrate_alias(
    manager,
    old_path,
    new_path,
    *,
    document_session_uuid=None,
    retain_old=False,
):
    del manager, old_path, new_path, document_session_uuid, retain_old
    return _legacy_lease_authority_removed()


def _compat_revoke(
    manager,
    document_session_uuid,
    *,
    reason,
    user_intervened=False,
):
    del manager, document_session_uuid, reason, user_intervened
    return _legacy_lease_authority_removed()


def _compat_apply_heartbeat_response(manager, response):
    del manager, response
    return _legacy_lease_authority_removed()


def _compat_credentials_snapshot(manager):
    del manager
    return _legacy_lease_authority_removed()


def _compat_build_request_context(
    manager,
    *,
    document_session_uuids=(),
    canonical_paths=(),
    operation_name="",
    task_id="",
    request_id=None,
):
    del (
        manager,
        document_session_uuids,
        canonical_paths,
        operation_name,
        task_id,
        request_id,
    )
    return _legacy_lease_authority_removed()


def _compat_build_heartbeat_payload(manager, current_operations=None):
    del manager, current_operations
    return _legacy_lease_authority_removed()


def _compat_build_heartbeat_request(
    manager,
    current_operations=None,
    *,
    request_id=None,
):
    del manager, current_operations, request_id
    return _legacy_lease_authority_removed()


def _compat_build_heartbeat_envelope(
    manager,
    current_operations=None,
    *,
    request_id=None,
):
    del manager, current_operations, request_id
    return _legacy_lease_authority_removed()


def _compat_redacted_status(manager):
    del manager
    return _legacy_lease_authority_removed()


def _compat_require_connected_locked(manager):
    del manager
    return _legacy_lease_authority_removed()


def _compat_require_open_locked(manager):
    del manager
    return _legacy_lease_authority_removed()


def _compat_build_heartbeat_payload_locked(manager, current_operations):
    del manager, current_operations
    return _legacy_lease_authority_removed()


def _compat_redact_text(manager, value, *, additional_secrets=()):
    del manager
    return _compat_redact_text_with_secrets(value, additional_secrets)


def _compat_redact_value(manager, value, *, additional_secrets=()):
    del manager

    def scrub(item):
        if isinstance(item, str):
            return _compat_redact_text_with_secrets(item, additional_secrets)
        if isinstance(item, dict):
            return {key: scrub(child) for key, child in item.items()}
        if isinstance(item, list):
            return [scrub(child) for child in item]
        if isinstance(item, tuple):
            return tuple(scrub(child) for child in item)
        return item

    return scrub(value)


def _compat_secret_snapshot_locked(manager):
    del manager
    return ()


def _compat_redact_text_with_secrets(value, secrets):
    safe = str(value)
    for secret in secrets:
        if secret:
            safe = safe.replace(str(secret), "[REDACTED]")
    return safe


def _compat_redact_text_locked(manager, value):
    del manager
    return str(value)
