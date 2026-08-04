"""One authenticated RPC request tracked by the inflight registry."""

from __future__ import annotations

import threading
from collections.abc import Iterable
from dataclasses import dataclass, field

from .cancellation_token import CancellationToken
from .inflight_lease_credential import InflightLeaseCredential


@dataclass
class InflightRequest:
    session_id: str
    request_id: str
    method: str
    token: CancellationToken
    _credentials: tuple[InflightLeaseCredential, ...] = field(
        default_factory=tuple, repr=False
    )
    _touched_credentials: tuple[InflightLeaseCredential, ...] = field(
        default_factory=tuple, repr=False
    )
    lease_affecting: bool = False
    _credential_lock: threading.RLock = field(
        default_factory=threading.RLock, init=False, repr=False, compare=False
    )

    @property
    def credentials(self) -> tuple[InflightLeaseCredential, ...]:
        with self._credential_lock:
            return self._credentials

    def add_credentials(
        self, credentials: Iterable[InflightLeaseCredential]
    ) -> None:
        with self._credential_lock:
            known = {
                (item.lease_id, item.document_session_uuid, item.generation)
                for item in self._credentials
            }
            additions = tuple(
                item
                for item in credentials
                if (item.lease_id, item.document_session_uuid, item.generation)
                not in known
            )
            self._credentials = self._credentials + additions

    @staticmethod
    def _credential_key(item: InflightLeaseCredential) -> tuple[str, str, int]:
        return item.lease_id, item.document_session_uuid, item.generation

    def touch_credentials(
        self, credentials: Iterable[InflightLeaseCredential]
    ) -> None:
        """Record only credentials whose documents this request authorized."""

        with self._credential_lock:
            known = {self._credential_key(item) for item in self._touched_credentials}
            additions = tuple(
                item
                for item in credentials
                if self._credential_key(item) not in known
            )
            self._touched_credentials = self._touched_credentials + additions

    @property
    def affected_credentials(self) -> tuple[InflightLeaseCredential, ...]:
        with self._credential_lock:
            return self._touched_credentials

    def scrub_credentials(self) -> None:
        with self._credential_lock:
            self._credentials = ()
            self._touched_credentials = ()
