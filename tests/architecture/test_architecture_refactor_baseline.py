"""Executable Phase 1 baseline and planned collaboration compatibility surface."""

from __future__ import annotations

import ast
import importlib
import inspect
import sys
from pathlib import Path

import pytest

from tests.helpers.architecture_authority import (
    authority_symbol_census as scan_authority_symbols,
    reachable_python_modules,
)
from tests.helpers.architecture_baseline import (
    FROZEN_DEPRECATION_RESULT,
    ROOT,
    _mutable_lease_call_target,
    dynamic_module_lookup_census,
    load_manifest,
    local_import_locator_census,
    mutable_lease_caller_census,
    rpc_mod_census,
)
from tests.helpers.runtime_bootstrap import bootstrap_unit_test_runtime

pytestmark = pytest.mark.unit

_FROZEN_AUTHORITY_DEPRECATIONS = {
    (
        "addon/FreeCADMCP/rpc_server/methods/lease_methods.py",
        symbol,
    )
    for symbol in (
        "heartbeat_document_lock",
        "lease_heartbeat_batch",
        "run_legacy_save",
        "run_typed_save",
    )
} | {
    (path, symbol)
    for path, symbols in {
        "addon/FreeCADMCP/rpc_server/rpc_server_ops/facade_bindings.py": (
            "heartbeat_document_lock",
            "lease_heartbeat_batch",
        ),
        "src/freecad_mcp/freecad_client_ops/connection_methods/connection_control_ops.py": (
            "heartbeat_document_locks_batch",
        ),
        "src/freecad_mcp/freecad_client_ops/connection_methods/connection_lease_ops.py": (
            "heartbeat_document_lock",
        ),
        "src/freecad_mcp/freecad_client_ops/facade_bindings.py": (
            "heartbeat_document_lock",
            "heartbeat_document_locks_batch",
        ),
        "src/freecad_mcp/operations/legacy_locking_deprecations.py": (
            "heartbeat_document_lock_operation",
        ),
        "src/freecad_mcp/server_ops/tool_exports/__init__.py": (
            "heartbeat_document_lock",
        ),
        "src/freecad_mcp/server_ops/tool_exports/bind_part_1.py": (
            "heartbeat_document_lock",
        ),
        "src/freecad_mcp/tools_lease_acquire_b.py": ("heartbeat_document_lock",),
    }.items()
    for symbol in symbols
}


def _module_name_for_path(path: str) -> str:
    module = path.removesuffix(".py").replace("/", ".")
    if module.endswith(".__init__"):
        module = module.removesuffix(".__init__")
    return module.removeprefix("src.")


def _is_frozen_authority_deprecation(record: dict[str, object]) -> bool:
    return (record["path"], record["symbol"]) in _FROZEN_AUTHORITY_DEPRECATIONS


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
    assert load_manifest()["verified_post_cutover"] is True
    production_files = [
        path
        for root in (ROOT / "addon/FreeCADMCP", ROOT / "src/freecad_mcp")
        for path in root.rglob("*.py")
    ]
    reachable = reachable_python_modules(
        root=ROOT,
        production_files=production_files,
        entrypoints=(
            "addon.FreeCADMCP.InitGui",
            "addon.FreeCADMCP.rpc_server.rpc_server",
            "freecad_mcp.server",
        ),
    )
    assert not {
        item["path"]
        for item in local_import_locator_census()
        if item["classification"] == "temporary_authority_locator"
        and _module_name_for_path(item["path"]) in reachable
    }
    assert all(
        item["classification"]
        in {
            "compatibility_alias",
            "generated_registration_locator",
            "module_probe",
            "registration_barrel",
            "runtime_dependency_locator",
            "runtime_locator",
        }
        for item in dynamic_module_lookup_census()
    )


def test_phase18_authority_inventory_is_historical_and_unreachable():
    manifest = load_manifest()
    allowances = manifest["temporary_authority_allowances"]
    assert manifest["manifest_state"] == "verified_post_cutover"
    assert manifest["verified_post_cutover"] is True
    assert {item["id"] for item in allowances} == {
        "core_authority",
        "locked_error_handoff_rotation",
        "lease_observers",
        "heartbeats",
        "sidecar_correctness",
        "mcp_save_recovery_authority",
    }
    for allowance in allowances:
        assert allowance["classification"] == "temporary_implementation"
        assert allowance["phase18_owner"] == "integrator"
        assert allowance["negative_end_state"]
    reachable = reachable_python_modules(
        root=ROOT,
        production_files=[
            path
            for root in (ROOT / "addon/FreeCADMCP", ROOT / "src/freecad_mcp")
            for path in root.rglob("*.py")
        ],
        entrypoints=(
            "addon.FreeCADMCP.InitGui",
            "addon.FreeCADMCP.rpc_server.rpc_server",
            "freecad_mcp.server",
        ),
    )
    forbidden = {
        module
        for module in reachable
        if any(
            marker in module
            for marker in (
                ".document_lock",
                ".lock_indicator",
                ".document_lease.core_authority",
                ".document_lease.observer",
                ".operations.locking",
                ".rpc_server.lease_runtime",
                ".server_ops.heartbeat",
                ".server_ops.stale_recovery_hooks",
                # Session elevation for actor-scoped GUI methods lives in
                # dispatch_core_enforcement_auth after Phase-16 GUI auth restore;
                # do not treat that live helper as cutover debt.
                ".dispatch_gui_lease_enforced",
                ".document_create_lease",
            )
        )
    }
    assert forbidden == set()
    census = scan_authority_symbols(
        root=ROOT,
        production_files=[
            path
            for root in (ROOT / "addon/FreeCADMCP", ROOT / "src/freecad_mcp")
            for path in root.rglob("*.py")
        ],
    )
    verified_reachable = {
        allowance["id"]: [
            record
            for record in census[allowance["id"]]
            if _module_name_for_path(record["path"]) in reachable
            and not _is_frozen_authority_deprecation(record)
        ]
        for allowance in allowances
    }
    assert verified_reachable == manifest["verified_reachable_authority"]


def test_mutable_lease_callers_are_not_reachable_after_phase18():
    manifest = load_manifest()
    allowance = manifest["phase7_mutable_lease_callers"]
    actual = mutable_lease_caller_census()

    assert allowance["classification"] == "temporary_implementation"
    assert allowance["phase18_owner"] == "integrator"
    assert allowance["negative_end_state"]
    reachable = reachable_python_modules(
        root=ROOT,
        production_files=[
            path
            for root in (ROOT / "addon/FreeCADMCP", ROOT / "src/freecad_mcp")
            for path in root.rglob("*.py")
        ],
        entrypoints=("addon.FreeCADMCP.document_lease",),
    )
    assert not {
        call["path"]
        for call in actual
        if any(
            call["path"].removesuffix(".py").replace("/", ".").endswith(module)
            for module in reachable
        )
    }


def test_historic_decoder_authority_exclusion_does_not_hide_new_writes(
    tmp_path: Path,
):
    historic_path = (
        tmp_path
        / "addon"
        / "FreeCADMCP"
        / "document_lease"
        / "historic_sidecar.py"
    )
    historic_path.parent.mkdir(parents=True)
    historic_path.write_text(
        """
def decode_historic_sidecar_bytes(data, sidecar_store, path, record):
    sidecar_store.create(path, record)
    return data

def unexpected_live_sidecar_write(sidecar_store, path, record):
    sidecar_store.create(path, record)
""".lstrip(),
        encoding="utf-8",
    )
    model_path = historic_path.with_name("model.py")
    model_path.write_text(
        """
def decode_historic_lease_record(data, authoritative_sidecar, path, record):
    authoritative_sidecar.replace(path, record)
    return data

class HistoricLeaseRecord:
    def injected_write(self, path, record):
        self._sidecar.create(path, record)
""".lstrip(),
        encoding="utf-8",
    )

    records = scan_authority_symbols(
        root=tmp_path,
        production_files=[historic_path, model_path],
    )["sidecar_correctness"]

    assert not any(
        record["symbol"] == "decode_historic_sidecar_bytes" for record in records
    )
    assert sum(record["symbol"] == "sidecar_store" for record in records) == 2
    assert any(record["symbol"] == "authoritative_sidecar" for record in records)
    assert any(record["symbol"] == "_sidecar" for record in records)


def test_frozen_deprecation_exclusion_does_not_hide_new_authority_symbol(
    tmp_path: Path,
) -> None:
    shim_path = (
        tmp_path
        / "src"
        / "freecad_mcp"
        / "freecad_client_ops"
        / "connection_methods"
        / "connection_lease_ops.py"
    )
    shim_path.parent.mkdir(parents=True)
    shim_path.write_text(
        """
def heartbeat_document_lock():
    return {"error_code": "LEGACY_LEASE_AUTHORITY_REMOVED"}

def unexpected_heartbeat_authority():
    rotate_live_heartbeat()
""".lstrip(),
        encoding="utf-8",
    )

    records = scan_authority_symbols(
        root=tmp_path,
        production_files=[shim_path],
    )["heartbeats"]
    visible = [record for record in records if not _is_frozen_authority_deprecation(record)]

    assert any(
        record["symbol"] == "unexpected_heartbeat_authority" for record in visible
    )
    assert all(record["symbol"] != "heartbeat_document_lock" for record in visible)


def test_mutable_lease_census_recognizes_store_aliases_without_string_false_positives():
    calls = {
        source: _mutable_lease_call_target(ast.parse(source).body[0].value)
        for source in (
            "store.create(path, record)",
            "store.delete(path, expected=record)",
            "writer.replace(path, record, expected=old)",
            "text.replace('a', 'b')",
        )
    }

    assert calls == {
        "store.create(path, record)": "SidecarStore.create",
        "store.delete(path, expected=record)": "SidecarStore.delete",
        "writer.replace(path, record, expected=old)": "SidecarStore.replace",
        "text.replace('a', 'b')": "",
    }


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


def _invoke_deprecation_contract(
    symbol: object, contract: list[dict[str, object]]
) -> object:
    args: list[object] = []
    kwargs: dict[str, object] = {}
    for parameter in contract:
        if not parameter["required"]:
            continue
        if parameter["kind"] in {"positional_only", "positional_or_keyword"}:
            args.append(object())
        elif parameter["kind"] == "keyword_only":
            kwargs[str(parameter["name"])] = object()
    return symbol(*args, **kwargs)


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
                result = _invoke_deprecation_contract(
                    symbol,
                    contract["parameter_contract"],
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
