"""Executable Phase 1 baseline and planned collaboration compatibility surface."""

from __future__ import annotations

import importlib
import inspect
import sys

import pytest

from tests.helpers.architecture_baseline import (
    FROZEN_DEPRECATION_RESULT,
    ROOT,
    authority_symbol_census,
    dynamic_module_lookup_census,
    load_manifest,
    local_import_locator_census,
    rpc_mod_census,
)
from tests.helpers.runtime_bootstrap import bootstrap_unit_test_runtime

pytestmark = pytest.mark.unit


def test_execution_revisions_and_adapter_only_compose_lane_are_frozen():
    baseline = load_manifest()["execution_baseline"]
    assert baseline["parent_revision"] == "863535a2d4b6c33b5bfce8171762320060a34afb"
    assert baseline["mcp_revision"] == "5357d0c16a64b4981a5f508bc83dd07ddf4f1ca6"
    assert baseline["native_collaboration_phases"] == [1, 2, 3, 4, 5, 6]
    assert baseline["compose_lane"]["decision"] == "adapter_only"
    assert baseline["compose_lane"]["collaboration_lane_required"] is True


def test_rpc_locator_census_matches_the_recorded_current_state():
    locator = load_manifest()["locator_census"]
    actual = rpc_mod_census()
    assert actual == locator["current_modules"]
    current_references = sum(
        item["loaded_references"]
        + item["import_bindings"]
        + item["exported_names"]
        for item in actual.values()
    )
    runtime_calls = sum(item["runtime_calls"] for item in actual.values())
    assert current_references == locator["current_references"]
    assert runtime_calls == locator["current_runtime_calls"]
    definitions = sum(item["definitions"] for item in actual.values())
    assert definitions == locator["current_definitions"]
    assert current_references + definitions == locator["current_locator_nodes"]
    assert locator["baseline_locator_nodes"] == 514
    assert locator["baseline_references"] == 504
    assert locator["baseline_runtime_calls"] == 432
    assert locator["current_locator_nodes"] <= locator["baseline_locator_nodes"]
    assert locator["current_references"] <= locator["baseline_references"]
    assert locator["current_runtime_calls"] <= locator["baseline_runtime_calls"]


def test_equivalent_dynamic_module_lookups_match_the_recorded_classifications():
    manifest = load_manifest()
    assert dynamic_module_lookup_census() == manifest["dynamic_module_lookups"]
    assert local_import_locator_census() == manifest["local_import_locators"]


def test_every_temporary_authority_has_a_phase18_owner_and_negative_assertion():
    manifest = load_manifest()
    allowances = manifest["temporary_authority_allowances"]
    assert manifest["manifest_state"] == "planned_pre_cutover"
    assert manifest["verified_post_cutover"] is False
    assert {item["id"] for item in allowances} == {
        "core_authority",
        "locked_error_handoff_rotation",
        "lease_observers",
        "heartbeats",
        "sidecar_correctness",
        "mcp_save_recovery_authority",
    }
    assert authority_symbol_census() == manifest["authority_symbol_census"]
    for allowance in allowances:
        assert allowance["classification"] == "temporary_implementation"
        assert allowance["phase18_owner"] == "integrator"
        assert allowance["negative_end_state"]
        census_paths = {
            record["path"]
            for record in manifest["authority_symbol_census"][allowance["id"]]
        }
        assert set(allowance["current_paths"]) == census_paths
        for path in allowance["current_paths"]:
            assert (ROOT / path).is_file(), (allowance["id"], path)

    sidecar_paths = {
        record["path"] for record in manifest["authority_symbol_census"]["sidecar_correctness"]
    }
    assert "addon/FreeCADMCP/git_sidecar.py" not in sidecar_paths
    assert "addon/FreeCADMCP/InitGui.py" not in sidecar_paths
    assert "addon/FreeCADMCP/document_lock_ops/eligibility.py" not in sidecar_paths
    save_paths = {
        record["path"]
        for record in manifest["authority_symbol_census"][
            "mcp_save_recovery_authority"
        ]
    }
    assert (
        "src/freecad_mcp/freecad_client_ops/json_rpc_http_transport.py"
        not in save_paths
    )


def _member_exists(module: object, qualified_name: str) -> bool:
    current = module
    for name in qualified_name.split("."):
        current = getattr(current, name, None)
        if current is None:
            return False
    return True


def _parameter_contract(value: object) -> list[dict[str, object]]:
    return [
        {
            "name": parameter.name,
            "kind": parameter.kind.name.lower(),
            "required": parameter.default is inspect.Signature.empty,
        }
        for parameter in inspect.signature(value).parameters.values()
    ]


def test_planned_compatibility_imports_resolve_with_frozen_symbols():
    bootstrap_unit_test_runtime()
    manifest = load_manifest()
    installed_addon_root = str(ROOT / "addon" / "FreeCADMCP")
    if installed_addon_root not in sys.path:
        sys.path.insert(0, installed_addon_root)
    for surface in manifest["retained_compatibility_surfaces"]:
        modules = [
            importlib.import_module(spelling)
            for spelling in [surface["module"], *surface["installed_aliases"]]
        ]
        assert len({module.__file__ for module in modules}) == 1
        for symbol in surface["current_symbols"]:
            values = [getattr(module, symbol) for module in modules]
            assert all(type(value).__name__ == type(values[0]).__name__ for value in values), (
                surface["module"],
                symbol,
            )
        for member in surface["planned_forbidden_members"]:
            assert _member_exists(modules[0], member) is not manifest[
                "verified_post_cutover"
            ]
        for contract in surface["post_cutover_deprecation_contracts"]:
            symbol = getattr(modules[0], contract["symbol"])
            assert callable(symbol)
            assert contract["exact_result"] == FROZEN_DEPRECATION_RESULT
            assert _parameter_contract(symbol) == contract["parameter_contract"]
            assert contract["phase18_representative_call_required"] is True
            if manifest["verified_post_cutover"]:
                invocation = contract["representative_call"]
                result = symbol(
                    *invocation["args"],
                    **invocation["kwargs"],
                )
                assert result == contract["exact_result"]


def test_frozen_public_lease_rpc_adapter_set_is_complete():
    bootstrap_unit_test_runtime()
    manifest = load_manifest()
    modules = [
        importlib.import_module("addon.FreeCADMCP.rpc_server.methods.lease_methods"),
        importlib.import_module("rpc_server.methods.lease_methods"),
    ]
    for module in modules:
        assert sorted(module.__all__) == manifest["public_lease_rpc_adapters"]
    for name in manifest["public_lease_rpc_adapters"]:
        assert all(callable(getattr(module, name)) for module in modules)


def test_native_collaboration_api_contract_is_recorded_for_the_branch_lane():
    native_api = load_manifest()["execution_baseline"]["native_api"]
    assert native_api["app_document_methods"] == [
        "canWriteRecoverySnapshot",
        "beginEditSession",
        "snapshotForEdit",
        "prepareEdit",
        "prepareEditAsync",
        "preparedEditStatus",
        "cancelPreparedEdit",
        "takePreparedEdit",
        "commitEdit",
        "cancelEdit",
        "editSessionStatus",
    ]
    assert native_api["app_module_methods"] == [
        "writeRecoverySnapshotToTransientDir",
        "advanceDocumentCollaborationEpoch",
    ]
    assert native_api["gui_document_methods"] == [
        "storePersonalViewContext",
        "getPersonalViewContext",
        "removePersonalViewContext",
        "renderPersonalViewContext",
    ]
    assert native_api["gui_python_binding_test"] == (
        "CollaborationDomainIntegrationTest.pythonPersonalContextStorageApiIsCallable"
    )
