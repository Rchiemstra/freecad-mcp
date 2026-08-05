"""Phase 18 tombstones for the retired release and lock-query authority."""

from __future__ import annotations

import pytest

from addon.FreeCADMCP.rpc_server.methods import lease_methods
from tests.helpers.architecture_baseline import FROZEN_DEPRECATION_RESULT

pytestmark = pytest.mark.unit


class _AuthorityTrap:
    def __getattribute__(self, name: str):
        raise AssertionError(f"tombstone touched retired authority: {name}")


@pytest.mark.parametrize(
    ("adapter", "args", "kwargs"),
    (
        (lease_methods.get_document_lock, (), {}),
        (lease_methods.list_document_locks, (), {}),
        (
            lease_methods.heartbeat_document_lock,
            ("historic-document-key", "historic-secret"),
            {},
        ),
        (lease_methods.release_document_lock, (), {}),
        (
            lease_methods.force_release_stale_lock,
            ("historic-document-key",),
            {},
        ),
        (
            lease_methods.update_document_lock,
            ({"document_name": "Historic"},),
            {},
        ),
    ),
)
def test_retired_release_and_query_adapters_return_fresh_frozen_tombstones(
    adapter,
    args,
    kwargs,
) -> None:
    facade = _AuthorityTrap()

    first = adapter(facade, *args, **kwargs)
    second = adapter(facade, *args, **kwargs)

    assert first == FROZEN_DEPRECATION_RESULT
    assert second == FROZEN_DEPRECATION_RESULT
    assert first is not second
    first["success"] = True
    assert second == FROZEN_DEPRECATION_RESULT


def test_retired_release_and_query_adapters_are_public_leaf_tombstones() -> None:
    source = lease_methods.__loader__.get_source(lease_methods.__name__)
    assert source is not None
    assert "lease_methods_ops" not in source
    assert "document_lease" not in source
    assert "import FreeCAD" not in source
    assert "from FreeCAD" not in source
