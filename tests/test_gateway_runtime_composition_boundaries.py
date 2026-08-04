"""Structural contracts for the transitional Phase 11 composition root."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.helpers.architecture_baseline import (
    authority_symbol_census,
    dynamic_module_lookup_census,
    load_manifest,
    local_import_locator_census,
    rpc_mod_census,
)
from tests.test_gateway_runtime_boundaries import _imports_gateway_runtime

ROOT = Path(__file__).resolve().parents[1]
ADDON_ROOT = ROOT / "addon" / "FreeCADMCP"
RUNTIME_PATH = ADDON_ROOT / "runtime.py"
LIFECYCLE_PATH = ADDON_ROOT / "rpc_server" / "server_lifecycle.py"
SHUTDOWN_PATH = ADDON_ROOT / "rpc_server" / "server_shutdown.py"
BUILDER_NAME = "_build_addon_runtime"
AUTHORITY_INVENTORIES = frozenset(
    {
        "core_authority",
        "heartbeats",
        "lease_observers",
        "locked_error_handoff_rotation",
        "mcp_save_recovery_authority",
        "sidecar_correctness",
    }
)
FROZEN_AUTHORITY_TOTALS = {
    "core_authority": 115,
    "heartbeats": 167,
    "lease_observers": 30,
    "locked_error_handoff_rotation": 15,
    "mcp_save_recovery_authority": 251,
    "sidecar_correctness": 861,
}

pytestmark = pytest.mark.unit


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _parents(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    return {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }


def _enclosing_function(
    node: ast.AST,
    parents: dict[ast.AST, ast.AST],
) -> str | None:
    current = parents.get(node)
    while current is not None:
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current.name
        current = parents.get(current)
    return None


def _static_all(tree: ast.Module) -> list[str] | None:
    assignments = [
        node
        for node in tree.body
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        and (
            (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "__all__"
            )
            or (
                isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.target.id == "__all__"
            )
        )
    ]
    if len(assignments) != 1:
        return None
    value = assignments[0].value
    if not isinstance(value, (ast.List, ast.Tuple)) or not all(
        isinstance(element, ast.Constant) and isinstance(element.value, str)
        for element in value.elts
    ):
        return None
    return [element.value for element in value.elts]


def _frozen_rpc_locator(
    tree: ast.Module,
    *,
    line: int,
) -> ast.ImportFrom:
    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.lineno == line
        and node.level == 1
        and node.module is None
        and [(alias.name, alias.asname) for alias in node.names]
        == [("rpc_server", "rpc_mod")]
    ]
    assert len(matches) == 1
    return matches[0]


def test_private_builder_is_a_top_level_non_exported_runtime_seam() -> None:
    tree = _parse(RUNTIME_PATH)
    builders = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == BUILDER_NAME
    ]

    assert len(builders) == 1
    assert isinstance(builders[0], ast.FunctionDef)
    assert _static_all(tree) == ["AddonRuntime"]


def test_startup_passes_only_the_private_builder_through_its_transitional_hook() -> None:
    tree = _parse(LIFECYCLE_PATH)
    parents = _parents(tree)
    locator = _frozen_rpc_locator(tree, line=108)
    imports = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and any(alias.name == BUILDER_NAME for alias in node.names)
    ]
    builder_references = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Load)
        and node.id == BUILDER_NAME
    ]

    assert imports
    for node in imports:
        assert node.module == "runtime"
        assert [(alias.name, alias.asname) for alias in node.names] == [
            (BUILDER_NAME, None)
        ]
        assert node.lineno > locator.lineno
        assert _enclosing_function(node, parents) == "start_rpc_server"
    assert len(builder_references) == 1
    reference = builder_references[0]
    assert reference.lineno > max(node.lineno for node in imports)
    assert _enclosing_function(reference, parents) == "start_rpc_server"
    hook_call = parents[reference]
    assert isinstance(hook_call, ast.Call)
    assert isinstance(hook_call.func, ast.Name)
    assert hook_call.func.id.startswith("_")
    assert hook_call.func.id.endswith("transitional_runtime")
    assert hook_call.args and hook_call.args[0] is reference

    hook_builders = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == hook_call.func.id
    ]
    assert len(hook_builders) == 1
    assert hook_builders[0].args.args
    assert hook_builders[0].args.args[0].arg == "builder"
    builder_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "builder"
    ]
    assert len(builder_calls) == 1


def test_frozen_start_and_stop_locators_remain_the_only_bootstrap_locators() -> None:
    start_tree = _parse(LIFECYCLE_PATH)
    stop_tree = _parse(SHUTDOWN_PATH)
    start_locator = _frozen_rpc_locator(start_tree, line=108)
    stop_locator = _frozen_rpc_locator(stop_tree, line=70)

    assert _enclosing_function(start_locator, _parents(start_tree)) == "start_rpc_server"
    assert _enclosing_function(stop_locator, _parents(stop_tree)) == "stop_rpc_server"


def test_gateway_layers_and_compatibility_surfaces_do_not_import_runtime() -> None:
    protected_files = {
        ADDON_ROOT / "InitGui.py",
        ADDON_ROOT / "rpc_server" / "rpc_server.py",
        SHUTDOWN_PATH,
        *sorted((ADDON_ROOT / "transport").rglob("*.py")),
        *sorted((ADDON_ROOT / "dispatch").rglob("*.py")),
        *sorted((ADDON_ROOT / "capabilities").rglob("*.py")),
        *sorted((ADDON_ROOT / "rpc_server" / "methods").rglob("*.py")),
    }
    findings = {
        path.relative_to(ROOT).as_posix(): [node.lineno for node in imports]
        for path in sorted(protected_files)
        if path.is_file()
        if (imports := _imports_gateway_runtime(_parse(path)))
    }

    assert findings == {}


def test_server_lifecycle_uses_no_barrel_or_dynamic_runtime_lookup() -> None:
    tree = _parse(LIFECYCLE_PATH)
    forbidden_imports = []
    forbidden_calls = []
    forbidden_module_lookups = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            forbidden_imports.extend(
                (node.lineno, alias.name)
                for alias in node.names
                if alias.name.partition(".")[0] in {"builtins", "importlib"}
            )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.partition(".")[0] in {"builtins", "importlib"}:
                forbidden_imports.append((node.lineno, module))
            if any(alias.name == BUILDER_NAME for alias in node.names):
                assert module == "runtime", "the builder must come from its defining leaf"
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "__import__":
                forbidden_calls.append(node.lineno)
            if isinstance(node.func, ast.Attribute) and node.func.attr == "import_module":
                forbidden_calls.append(node.lineno)
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "sys"
            and node.attr == "modules"
        ):
            forbidden_module_lookups.append(node.lineno)

    assert forbidden_imports == []
    assert forbidden_calls == []
    assert forbidden_module_lookups == []


def test_phase11_keeps_the_exact_frozen_runtime_locator_inventories() -> None:
    manifest = load_manifest()
    locator = manifest["locator_census"]
    actual = rpc_mod_census()

    assert actual == locator["current_modules"]
    assert sum(item["definitions"] for item in actual.values()) == locator[
        "current_definitions"
    ]
    assert sum(
        item["loaded_references"]
        + item["import_bindings"]
        + item["exported_names"]
        for item in actual.values()
    ) == locator["current_references"]
    assert sum(item["runtime_calls"] for item in actual.values()) == locator[
        "current_runtime_calls"
    ]
    assert dynamic_module_lookup_census() == manifest["dynamic_module_lookups"]
    assert local_import_locator_census() == manifest["local_import_locators"]


def test_phase11_keeps_all_six_authority_inventories_byte_exact() -> None:
    manifest = load_manifest()
    expected = manifest["authority_symbol_census"]
    actual = authority_symbol_census()

    assert set(expected) == AUTHORITY_INVENTORIES
    assert {name: len(records) for name, records in expected.items()} == (
        FROZEN_AUTHORITY_TOTALS
    )
    assert actual == expected
