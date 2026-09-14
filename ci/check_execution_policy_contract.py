#!/usr/bin/env python3
"""Fast completeness gate for CAD execution policy registries."""

from __future__ import annotations

import ast
import importlib.util
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "src"))

from freecad_mcp.capabilities.load import all_subject_manifests  # noqa: E402
from freecad_mcp.capabilities.schema import ExecutionPolicy, MutationClass, ToolEntry  # noqa: E402

_FORBIDDEN_REGISTRY_NAMES = frozenset(
    {"execute_code", "execute_code_async", "run_transaction"}
)
_NON_CAD_REGISTER_PREFIXES = ("tools_lease", "tools_runtime", "tools_worker")


def _load_addon_execution_policies(root: Path) -> dict[str, str]:
    path = (
        root
        / "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/execution_policies.py"
    )
    spec = importlib.util.spec_from_file_location(
        "addon_execution_policies_gate",
        path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load addon execution policies from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    policies = getattr(module, "EXECUTION_POLICIES")
    return {name: policy.value for name, policy in policies.items()}


def _load_mcp_execution_policies() -> dict[str, str]:
    from freecad_mcp.capabilities.execution_policies import EXECUTION_POLICIES

    return {name: policy.value for name, policy in EXECUTION_POLICIES.items()}


def scan_typed_rpc_handler_names(root: Path) -> set[str]:
    """AST-scan cad_methods_ops leaf modules for ``TYPED_RPC_HANDLER`` names."""

    ops_dir = root / "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops"
    names: set[str] = set()
    for path in sorted(ops_dir.glob("*.py")):
        if path.name in {"execution_policies.py", "cad_dependencies.py"}:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if not isinstance(target, ast.Name) or target.id != "TYPED_RPC_HANDLER":
                    continue
                if not isinstance(node.value, ast.Tuple) or not node.value.elts:
                    continue
                first = node.value.elts[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    names.add(first.value)
    return names


def is_cad_tool(entry: ToolEntry) -> bool:
    if entry.mutation_class in {MutationClass.LEASE, MutationClass.EXECUTION}:
        return False
    register_module = entry.register_module or ""
    return not register_module.startswith(_NON_CAD_REGISTER_PREFIXES)


def scan_execution_policy_completeness(
    root: Path,
    *,
    addon_policies: Mapping[str, str] | None = None,
    mcp_policies: Mapping[str, str] | None = None,
    typed_rpc_names: set[str] | None = None,
    tool_entries: Sequence[ToolEntry] | None = None,
) -> list[str]:
    """Return violation messages for execution-policy registry completeness."""

    violations: list[str] = []
    addon = dict(addon_policies or _load_addon_execution_policies(root))
    mcp = dict(mcp_policies or _load_mcp_execution_policies())
    typed_names = typed_rpc_names or scan_typed_rpc_handler_names(root)

    if tool_entries is None:
        from tests.helpers.runtime_bootstrap import bootstrap_unit_test_runtime

        bootstrap_unit_test_runtime()
        tool_entries = [
            entry for manifest in all_subject_manifests() for entry in manifest.tools
        ]

    cad_tool_names = {entry.name for entry in tool_entries if is_cad_tool(entry)}
    required_names = typed_names | cad_tool_names

    schema_values = {member.value for member in ExecutionPolicy}
    addon_enum_path = (
        root
        / "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/execution_policies.py"
    )
    addon_tree = ast.parse(
        addon_enum_path.read_text(encoding="utf-8"),
        filename=str(addon_enum_path),
    )
    addon_values: set[str] = set()
    for node in addon_tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != "ExecutionPolicy":
            continue
        for item in node.body:
            if not isinstance(item, ast.Assign):
                continue
            for target in item.targets:
                if isinstance(target, ast.Name):
                    value = item.value
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        addon_values.add(value.value)
    if addon_values != schema_values:
        violations.append(
            "execution policy enum values differ between schema and addon mirror"
        )

    for forbidden in sorted(_FORBIDDEN_REGISTRY_NAMES):
        if forbidden in addon:
            violations.append(f"forbidden execution policy registry entry in addon: {forbidden}")
        if forbidden in mcp:
            violations.append(f"forbidden execution policy registry entry in MCP: {forbidden}")

    missing_addon = sorted(required_names - addon.keys())
    missing_mcp = sorted(required_names - mcp.keys())
    for name in missing_addon:
        violations.append(f"missing execution policy in addon registry: {name}")
    for name in missing_mcp:
        violations.append(f"missing execution policy in MCP registry: {name}")

    extra_addon = sorted(addon.keys() - required_names)
    extra_mcp = sorted(mcp.keys() - required_names)
    for name in extra_addon:
        violations.append(f"extra execution policy in addon registry: {name}")
    for name in extra_mcp:
        violations.append(f"extra execution policy in MCP registry: {name}")

    for name in sorted(required_names):
        addon_value = addon.get(name)
        mcp_value = mcp.get(name)
        if addon_value is None or mcp_value is None:
            continue
        if addon_value != mcp_value:
            violations.append(
                f"execution policy registries disagree for {name}: "
                f"addon={addon_value!r} mcp={mcp_value!r}"
            )

    for entry in tool_entries:
        expected = mcp.get(entry.name)
        if is_cad_tool(entry):
            if entry.execution_policy is None:
                violations.append(f"CAD ToolEntry missing execution_policy: {entry.name}")
                continue
            if entry.execution_policy.value != expected:
                violations.append(
                    f"ToolEntry execution_policy mismatch for {entry.name}: "
                    f"manifest={entry.execution_policy.value!r} registry={expected!r}"
                )
        elif entry.execution_policy is not None:
            violations.append(
                f"non-CAD ToolEntry must not declare execution_policy: {entry.name}"
            )

    return violations


def _policy_counts(policies: Mapping[str, str]) -> Counter[str]:
    return Counter(policies.values())


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    root = Path(__file__).resolve().parents[1]
    violations = scan_execution_policy_completeness(root)
    for violation in violations:
        print(violation, file=sys.stderr)
    if violations:
        return 1

    addon = _load_addon_execution_policies(root)
    counts = _policy_counts(addon)
    print(
        "execution policy contract: OK "
        f"(152 names; "
        f"DOCUMENT_MUTATION={counts['document_mutation']}, "
        f"DOCUMENT_QUERY={counts['document_query']}, "
        f"DOCUMENT_LIFECYCLE={counts['document_lifecycle']}, "
        f"HISTORY_OPERATION={counts['history_operation']}, "
        f"EXTERNAL_EFFECT={counts['external_effect']}, "
        f"GUI_GLOBAL={counts['gui_global']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
