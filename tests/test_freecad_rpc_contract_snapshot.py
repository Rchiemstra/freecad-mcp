"""Frozen contract snapshot for ``FreeCADRPC`` public XML-RPC surface."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from tests.helpers.runtime_bootstrap import bootstrap_unit_test_runtime

pytestmark = pytest.mark.unit

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "freecad_rpc_contract_snapshot.json"


def _load_snapshot() -> dict[str, dict[str, str]]:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def _capture_public_methods(cls: type) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for name in sorted(dir(cls)):
        if name.startswith("_"):
            continue
        attr = getattr(cls, name)
        if not callable(attr):
            continue
        out[name] = {
            "signature": str(inspect.signature(attr)),
            "docstring": inspect.getdoc(attr) or "",
        }
    return out


def _xmlrpc_exposed_names(instance) -> frozenset[str]:
    """Names discoverable the same way ``register_instance`` publishes methods."""

    return frozenset(
        name
        for name in dir(instance)
        if not name.startswith("_") and callable(getattr(instance, name))
    )


@pytest.fixture(scope="module")
def freecad_rpc_class():
    bootstrap_unit_test_runtime()
    from addon.FreeCADMCP.rpc_server.rpc_server import FreeCADRPC

    return FreeCADRPC


def test_freecad_rpc_public_surface_matches_contract_snapshot(freecad_rpc_class):
    expected = _load_snapshot()["public_methods"]
    actual = _capture_public_methods(freecad_rpc_class)
    assert actual == expected


def test_freecad_rpc_instance_exposes_same_public_names(freecad_rpc_class):
    expected_names = frozenset(_load_snapshot()["public_methods"])
    instance = freecad_rpc_class()
    assert _xmlrpc_exposed_names(instance) == expected_names
