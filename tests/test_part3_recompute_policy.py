"""Part 3 explicit recompute registry completeness (ADR §5 / §11.7)."""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from addon.FreeCADMCP.rpc_server import recompute_policy
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import cad_mutation
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import references

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_GATEWAY = (
    _ROOT
    / "addon"
    / "FreeCADMCP"
    / "generated"
    / "capabilities"
    / "gateway_dispatch.json"
)


def _gateway_mutation_methods() -> frozenset[str]:
    payload = json.loads(_GATEWAY.read_text(encoding="utf-8"))
    return frozenset(
        entry["rpc_method"]
        for entry in payload["entries"]
        if entry.get("mutation_class") == "mutation"
    )


def _gateway_read_methods() -> frozenset[str]:
    payload = json.loads(_GATEWAY.read_text(encoding="utf-8"))
    return frozenset(
        entry["rpc_method"]
        for entry in payload["entries"]
        if entry.get("mutation_class") == "read"
    )


def test_every_gateway_mutation_has_exactly_one_recompute_policy_declaration():
    mutation_methods = _gateway_mutation_methods()
    assert mutation_methods == recompute_policy.mutation_rpc_methods()
    for method in sorted(mutation_methods):
        policy = recompute_policy.declared_policy(method)
        assert policy is not None, method
        assert policy in {
            recompute_policy.RecomputePolicy.NONE,
            recompute_policy.RecomputePolicy.TARGET,
        }


def test_read_only_gateway_methods_declare_no_recompute_policy():
    for method in _gateway_read_methods():
        assert recompute_policy.declared_policy(method) is None


def test_public_execute_code_default_remains_none():
    from freecad_mcp import execute_options
    from freecad_mcp.generated.capabilities.register_modules import tools_core_execute
    from freecad_mcp.operations.core_ops import execute_ops

    assert execute_options.ExecuteOptions().recompute == "none"
    execute_source = inspect.getsource(execute_ops.execute_code_operation)
    assert 'recompute: str = "none"' in execute_source
    tools_path = Path(tools_core_execute.__file__)
    tools_source = tools_path.read_text(encoding="utf-8")
    assert 'recompute: str = "none"' in tools_source
    execute_module = Path(__file__).resolve().parents[1] / (
        "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/execute_code.py"
    )
    assert 'options.get("recompute", "none")' in execute_module.read_text(encoding="utf-8")


def test_run_cad_mutation_asserts_registry_match():
    collaborators = object()
    with pytest.raises(RuntimeError, match="native_recompute mismatch"):
        cad_mutation.run_cad_mutation(
            collaborators,
            "Model",
            lambda: True,
            native_recompute=True,
            method="repair_references",
        )


def test_repair_references_pins_none_and_refuses_recompute_true():
    rpc = MagicMock()
    rpc._cad_collaborators = MagicMock()
    rpc._dispatch_gui = lambda task: task()

    result = references.repair_references(
        rpc,
        "Model",
        [{"object": "Binder", "property": "Support", "references": []}],
        recompute=True,
    )

    assert result["success"] is False
    assert result["error_code"] == "RECOMPUTE_DEFERRED"
    assert recompute_policy.declared_policy("repair_references") is (
        recompute_policy.RecomputePolicy.NONE
    )


def test_adr_lifecycle_mutations_declare_none_not_target():
    for method in ("create_document", "close_document"):
        assert recompute_policy.declared_policy(method) is (
            recompute_policy.RecomputePolicy.NONE
        )
