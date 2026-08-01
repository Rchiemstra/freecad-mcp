"""LeaseClientManager method implementations."""

from __future__ import annotations

import threading

from .lease_credential import LeaseCredential
from .lease_revocation import LeaseRevocation


def init_manager(manager, *, session_token: str | None = None) -> None:
        manager._lock = threading.RLock()
        manager._credentials: dict[str, LeaseCredential] = {}
        manager._alias_to_session: dict[str, str] = {}
        manager._session_aliases: dict[str, set[str]] = {}
        manager._revocations: dict[str, LeaseRevocation] = {}
        manager._session_token = session_token
        manager._connected = bool(session_token)
        manager._closed = False
        manager._disconnect_reason = ""
        manager._disconnected_at: str | None = None
