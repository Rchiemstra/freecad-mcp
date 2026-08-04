"""Focused contracts for the stdlib-only dispatch registries."""

from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import pytest

from addon.FreeCADMCP.dispatch.cancellation_token import CancellationToken
from addon.FreeCADMCP.dispatch.continuations import (
    BoundedContinuationRegistry,
    ContinuationCapacityError,
)
from addon.FreeCADMCP.dispatch.inflight_lease_credential import (
    InflightLeaseCredential,
)
from addon.FreeCADMCP.dispatch.inflight_request_registry import (
    InflightRequestRegistry,
)

pytestmark = pytest.mark.unit


def _uuid() -> str:
    return str(uuid.uuid4())


def _credential(token: str) -> InflightLeaseCredential:
    return InflightLeaseCredential(
        lease_id=_uuid(),
        document_session_uuid=_uuid(),
        generation=3,
        token=token,
        mcp_instance_id=_uuid(),
    )


def test_cancellation_resolution_has_one_concurrent_owner_and_fresh_cache() -> None:
    token = CancellationToken(_uuid(), _uuid(), "save_document")
    callers = 24
    barrier = threading.Barrier(callers)

    def claim() -> tuple[bool, object]:
        barrier.wait(timeout=5)
        return token.claim_cancellation_resolution()

    with ThreadPoolExecutor(max_workers=callers) as executor:
        claims = [future.result(timeout=5) for future in [
            executor.submit(claim) for _ in range(callers)
        ]]

    assert sum(claimed for claimed, _cached in claims) == 1
    assert all(cached is None for _claimed, cached in claims)
    expected = [{"state": "cancelled", "revision": 8}]
    assert token.finish_cancellation_resolution(expected) == expected
    claimed, cached = token.claim_cancellation_resolution()
    assert claimed is False
    assert cached == expected
    cached[0]["state"] = "tampered"
    assert token.cancellation_resolution() == expected


def test_terminal_tombstones_are_bounded_after_credentials_are_scrubbed() -> None:
    registry = InflightRequestRegistry(max_terminal_entries=2)
    session_id = _uuid()
    requests = []
    for index in range(3):
        request = registry.register(
            session_id,
            f"request-{index}",
            "create_object",
            (_credential(f"secret-{index}"),),
        )
        request.touch_credentials(request.credentials)
        requests.append(request)
        snapshot = registry.finish_handler(
            session_id,
            request.request_id,
            status="completed",
        )
        assert snapshot is not None and snapshot.terminal
        assert request.credentials == ()
        assert request.affected_credentials == ()

    assert registry.status(session_id, "request-0") is None
    assert registry.status(session_id, "request-1") is not None
    assert registry.status(session_id, "request-2") is not None
    assert registry.active_count == 0


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"max_entries": 0}, "max_entries"),
        ({"max_entries": False}, "max_entries"),
        ({"max_entries": 0.5}, "max_entries"),
        ({"max_entries": 1.5}, "max_entries"),
        ({"ttl_seconds": 0}, "ttl_seconds"),
        ({"ttl_seconds": float("inf")}, "ttl_seconds"),
    ],
)
def test_continuation_bounds_must_be_positive_and_finite(
    kwargs: dict[str, object], match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        BoundedContinuationRegistry(**kwargs)


def test_continuation_expiry_uses_exact_injected_clock_edge_and_prunes_globally() -> None:
    now = [10.0]
    registry: BoundedContinuationRegistry[str, object] = BoundedContinuationRegistry(
        max_entries=3,
        ttl_seconds=5.0,
        monotonic=lambda: now[0],
    )
    first = object()
    second = object()
    registry.begin("first", first)
    registry.begin("second", second)

    now[0] = 14.999
    assert registry.get("first") is first
    now[0] = 15.0
    assert registry.get("missing") is None
    assert registry.get("first") is None
    assert registry.get("second") is None
    assert registry.count == 0


@dataclass
class _Continuation:
    name: str
    protected: bool = False
    updates: int = 0


def _registry(
    now: list[float], *, max_entries: int = 2, ttl_seconds: float = 10.0
) -> BoundedContinuationRegistry[str, _Continuation]:
    return BoundedContinuationRegistry(
        max_entries=max_entries,
        ttl_seconds=ttl_seconds,
        monotonic=lambda: now[0],
        is_protected=lambda entry: entry.protected,
    )


def test_continuation_eviction_is_deterministic_and_apply_refreshes_recency() -> None:
    now = [0.0]
    registry = _registry(now)
    first = registry.begin("first", _Continuation("first"))
    now[0] = 1.0
    registry.begin("second", _Continuation("second"))
    now[0] = 2.0
    assert registry.apply("first", lambda entry: entry.name) == "first"
    now[0] = 3.0
    third = registry.begin("third", _Continuation("third"))

    assert registry.get("first") is first
    assert registry.get("second") is None
    assert registry.get("third") is third


def test_duplicate_live_key_is_rejected_without_replacing_exact_value() -> None:
    now = [0.0]
    registry = _registry(now)
    original = registry.begin("same", _Continuation("original"))

    with pytest.raises(ValueError, match="already registered"):
        registry.begin("same", _Continuation("replacement"))

    assert registry.get("same") is original
    now[0] = 10.0
    replacement = registry.begin("same", _Continuation("after-expiry"))
    assert registry.get("same") is replacement


def test_protected_entries_never_expire_or_yield_capacity_and_full_fails_closed() -> None:
    now = [0.0]
    registry = _registry(now)
    first = registry.begin("first", _Continuation("first", protected=True))
    second = registry.begin("second", _Continuation("second", protected=True))
    now[0] = 100.0

    with pytest.raises(ContinuationCapacityError, match="protected"):
        registry.begin("third", _Continuation("third"))

    assert registry.count == 2
    assert registry.get("first") is first
    assert registry.get("second") is second
    assert registry.get("third") is None


def test_atomic_apply_serializes_mutations_and_discard_updates_count() -> None:
    now = [0.0]
    registry = _registry(now, max_entries=1)
    value = registry.begin("counter", _Continuation("counter"))
    callers = 20
    barrier = threading.Barrier(callers)

    def increment() -> None:
        barrier.wait(timeout=5)

        def mutate(entry: _Continuation) -> None:
            previous = entry.updates
            time.sleep(0)
            entry.updates = previous + 1

        registry.apply("counter", mutate)

    with ThreadPoolExecutor(max_workers=callers) as executor:
        futures = [executor.submit(increment) for _ in range(callers)]
        for future in futures:
            future.result(timeout=5)

    assert value.updates == callers
    assert registry.count == 1
    assert registry.discard("counter") is True
    assert registry.discard("counter") is False
    assert registry.count == 0
    with pytest.raises(KeyError):
        registry.apply("counter", lambda entry: entry)


def test_failed_apply_does_not_refresh_expiry_or_eviction_recency() -> None:
    now = [0.0]
    registry = _registry(now, ttl_seconds=5.0)
    first = registry.begin("first", _Continuation("first"))
    now[0] = 1.0
    second = registry.begin("second", _Continuation("second"))
    now[0] = 4.0

    def fail(_entry: _Continuation) -> None:
        raise RuntimeError("policy transition failed")

    with pytest.raises(RuntimeError, match="policy transition failed"):
        registry.apply("first", fail)

    now[0] = 4.5
    third = registry.begin("third", _Continuation("third"))
    assert registry.get("first") is None
    assert registry.get("second") is second
    assert registry.get("third") is third
    assert first.name == "first"
