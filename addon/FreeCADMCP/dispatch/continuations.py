"""Generic bounded storage for process-local continuation state."""

from __future__ import annotations

import math
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from typing import Generic, TypeVar

Key = TypeVar("Key", bound=Hashable)
Value = TypeVar("Value")
Result = TypeVar("Result")


class ContinuationCapacityError(RuntimeError):
    """No unprotected continuation can be removed to admit new state."""


@dataclass(slots=True)
class _StoredContinuation(Generic[Value]):
    value: Value
    updated_at: float


class BoundedContinuationRegistry(Generic[Key, Value]):
    """Bound arbitrary continuation values without owning their state policy.

    Injected predicates classify values that may not yield capacity and, when
    needed, the subset that may not expire. By default one predicate protects
    both policies. Successful ``apply`` calls refresh recency while holding the
    same lock used by lookup, admission, expiry, and eviction.
    """

    def __init__(
        self,
        *,
        max_entries: int = 256,
        ttl_seconds: float = 3600.0,
        monotonic: Callable[[], float] = time.monotonic,
        is_protected: Callable[[Value], bool] | None = None,
        is_expiry_protected: Callable[[Value], bool] | None = None,
    ) -> None:
        if (
            isinstance(max_entries, bool)
            or not isinstance(max_entries, int)
            or max_entries <= 0
        ):
            raise ValueError("max_entries must be a positive integer")
        ttl = float(ttl_seconds)
        if not math.isfinite(ttl) or ttl <= 0:
            raise ValueError("ttl_seconds must be positive and finite")
        if not callable(monotonic):
            raise TypeError("monotonic must be callable")
        if is_protected is not None and not callable(is_protected):
            raise TypeError("is_protected must be callable")
        if is_expiry_protected is not None and not callable(is_expiry_protected):
            raise TypeError("is_expiry_protected must be callable")
        self._max_entries = int(max_entries)
        self._ttl_seconds = ttl
        self._monotonic = monotonic
        self._is_protected = is_protected or (lambda _value: False)
        self._is_expiry_protected = is_expiry_protected or self._is_protected
        self._entries: OrderedDict[Key, _StoredContinuation[Value]] = OrderedDict()
        self._lock = threading.RLock()

    def _now(self) -> float:
        return float(self._monotonic())

    def _prune_expired_locked(self, now: float) -> None:
        for key, stored in tuple(self._entries.items()):
            if self._is_expiry_protected(stored.value):
                continue
            if now - stored.updated_at >= self._ttl_seconds:
                self._entries.pop(key, None)

    def _evict_oldest_unprotected_locked(self) -> None:
        for key, stored in self._entries.items():
            if not self._is_protected(stored.value):
                self._entries.pop(key)
                return
        raise ContinuationCapacityError(
            "continuation registry is full of protected entries"
        )

    def begin(self, key: Key, value: Value) -> Value:
        """Insert a new value without replacing a live value at *key*."""

        with self._lock:
            now = self._now()
            self._prune_expired_locked(now)
            if key in self._entries:
                raise ValueError("continuation key is already registered")
            while len(self._entries) >= self._max_entries:
                self._evict_oldest_unprotected_locked()
            self._entries[key] = _StoredContinuation(value=value, updated_at=now)
            return value

    def get(self, key: Key) -> Value | None:
        """Return the exact stored value after globally pruning expiry."""

        with self._lock:
            self._prune_expired_locked(self._now())
            stored = self._entries.get(key)
            return None if stored is None else stored.value

    def apply(
        self,
        key: Key,
        operation: Callable[[Value], Result],
    ) -> Result:
        """Apply *operation* atomically and refresh the value's recency.

        Missing or expired keys raise ``KeyError``. The value remains the exact
        object supplied to ``begin``; the registry adds synchronization and
        lifecycle mechanics without copying or interpreting policy state.
        """

        if not callable(operation):
            raise TypeError("operation must be callable")
        with self._lock:
            self._prune_expired_locked(self._now())
            stored = self._entries.get(key)
            if stored is None:
                raise KeyError(key)
            result = operation(stored.value)
            stored.updated_at = self._now()
            self._entries.move_to_end(key)
            return result

    def discard(self, key: Key) -> bool:
        """Remove *key* regardless of policy state."""

        with self._lock:
            return self._entries.pop(key, None) is not None

    @property
    def count(self) -> int:
        with self._lock:
            self._prune_expired_locked(self._now())
            return len(self._entries)
