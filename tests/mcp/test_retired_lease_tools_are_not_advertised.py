"""Retired document-lease tools must not appear in the MCP tool list."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from freecad_mcp.capabilities.load import all_subject_manifests
from tests.helpers.runtime_bootstrap import bootstrap_unit_test_runtime

pytestmark = pytest.mark.unit

RETIRED_LEASE_TOOLS = frozenset(
    {
        "acquire_document_lock",
        "adopt_dirty_document",
        "claim_acquisition_result",
        "get_document_lock",
        "list_document_locks",
        "release_document_lock",
        "update_document_lock",
    }
)

_ROOT = Path(__file__).resolve().parents[2]
_SNAPSHOT = _ROOT / "tests" / "fixtures" / "mcp_tool_registry_contract_snapshot.json"
_GATEWAY = (
    _ROOT / "src" / "freecad_mcp" / "generated" / "capabilities" / "gateway_dispatch.json"
)


def _tool_registry(mcp) -> dict:
    manager = getattr(mcp, "_tool_manager", None)
    assert manager is not None
    registry = getattr(manager, "_tools", None) or getattr(manager, "tools", None)
    assert isinstance(registry, dict)
    return registry


@pytest.fixture(scope="module")
def server_module():
    bootstrap_unit_test_runtime()
    from freecad_mcp import server

    return server


def test_retired_lease_tools_are_absent_from_the_mcp_registry(server_module):
    advertised = RETIRED_LEASE_TOOLS & set(_tool_registry(server_module.mcp))
    assert advertised == set()


def test_retired_lease_tools_are_absent_from_schemas_and_exports():
    snapshot = json.loads(_SNAPSHOT.read_text(encoding="utf-8"))
    gateway = json.loads(_GATEWAY.read_text(encoding="utf-8"))
    manifest_tools = {
        entry.name for manifest in all_subject_manifests() for entry in manifest.tools
    }
    from freecad_mcp.server_ops.tool_exports.export_names import __all__ as export_names

    assert RETIRED_LEASE_TOOLS.isdisjoint(snapshot["tool_order"])
    assert RETIRED_LEASE_TOOLS.isdisjoint(snapshot["tools"])
    assert RETIRED_LEASE_TOOLS.isdisjoint(manifest_tools)
    assert RETIRED_LEASE_TOOLS.isdisjoint(
        item["tool"] for item in gateway["entries"]
    )
    assert RETIRED_LEASE_TOOLS.isdisjoint(export_names)
