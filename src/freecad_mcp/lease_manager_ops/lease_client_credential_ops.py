"""Compatibility exports for LeaseClientManager credential operations."""

from .lease_client_manager import (  # noqa: I001 - preserve the historic member order.
    _compat_add_alias as add_alias,
    _compat_aliases_for as aliases_for,
    _compat_close as close,
    _compat_get as get,
    _compat_mark_connected as mark_connected,
    _compat_mark_disconnected as mark_disconnected,
    _compat_migrate_alias as migrate_alias,
    _compat_require as require,
    _compat_revoke as revoke,
    _compat_store as store,
)

__all__ = (  # noqa: RUF022 - preserve the historic public member order.
    "mark_connected",
    "close",
    "mark_disconnected",
    "store",
    "get",
    "require",
    "aliases_for",
    "add_alias",
    "migrate_alias",
    "revoke",
)
