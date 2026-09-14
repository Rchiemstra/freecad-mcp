#!/usr/bin/env python3
"""Fast static and architecture gate for the typed ``run_fem_analysis`` slice."""

from __future__ import annotations

import ast
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from ci.discover_typed_slice import run_discovered_mypy


_LEAF = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/run_fem_analysis.py"
_MUTATION = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/run_fem_analysis_mutation.py"
_PUBLIC_ADAPTER = "src/freecad_mcp/operations/parametric_ops/run_fem_analysis.py"
_ADDON_CONTRACT = "addon/FreeCADMCP/_shared/protocol/run_fem_analysis_contract.py"
_CLIENT_CONTRACT = "src/freecad_mcp/_shared/protocol/run_fem_analysis_contract.py"
_TEMPLATE = ""


def _source(root: Path, relative: str, overrides: Mapping[str, str]) -> str:
    return overrides.get(relative, (root / relative).read_text(encoding="utf-8"))


def _function(tree: ast.AST, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise ValueError(f"missing function {name}")


def _class_method(tree: ast.Module, class_name: str, method_name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for member in ast.walk(node):
                if isinstance(member, ast.FunctionDef) and member.name == method_name:
                    return member
    raise ValueError(f"missing method {class_name}.{method_name}")


def _called_names(node: ast.AST) -> list[str]:
    names: list[str] = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if isinstance(child.func, ast.Name):
            names.append(child.func.id)
        elif isinstance(child.func, ast.Attribute):
            names.append(child.func.attr)
    return names


def _scan_leaf(source: str) -> list[str]:
    tree = ast.parse(source, filename=_LEAF)
    apply_function = _function(tree, "apply_run_fem_analysis")
    apply_closure = _class_method(tree, "_RunFemAnalysisExecution", "apply")
    run_function = _class_method(tree, "_RunFemAnalysisExecution", "run")
    forbidden = {
        "abortTransaction",
        "commitTransaction",
        "execute_code",
        "exec",
        "openTransaction",
        "recompute",
        "run_transaction",
    }
    found = sorted(forbidden & set(_called_names(apply_function)))
    violations = ["RUN_FEM_ANALYSIS001 leaf owns forbidden execution: " + ", ".join(found)] if found else []
    if "inspect" in _called_names(apply_closure):
        violations.append("RUN_FEM_ANALYSIS002 inspection runs inside apply")
    mutation_calls = [
        node
        for node in ast.walk(run_function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "run_run_fem_analysis_native_mutation"
    ]
    if len(mutation_calls) != 1:
        return [*violations, "RUN_FEM_ANALYSIS003 must use exactly one typed mutation call"]
    call = mutation_calls[0]
    postcondition = call.args[3] if len(call.args) > 3 else None
    if not (isinstance(postcondition, ast.Attribute) and postcondition.attr == "inspect"):
        violations.append("RUN_FEM_ANALYSIS004 missing typed postcondition=inspect")
    return violations


def _scan_native_release(source: str) -> list[str]:
    tree = ast.parse(source, filename=_MUTATION)
    native_result = _function(tree, "_run_fem_analysis_native_result")
    runner = _function(tree, "run_run_fem_analysis_native_mutation")
    violations = []
    import types

    module = types.ModuleType("addon.FreeCADMCP.rpc_server.methods.cad_methods_ops._run_fem_analysis_gate")
    module.__package__ = "addon.FreeCADMCP.rpc_server.methods.cad_methods_ops"
    sys.modules[module.__name__] = module
    try:
        exec(compile(tree, _MUTATION, "exec"), module.__dict__)
        state = module._NativeMutationState(postcondition_passed=True)
        for status in (
            "Busy",
            "ApplyFailed",
            "PostconditionFailed",
            "PublicationFailed",
            "RollbackFailed",
        ):
            result = module._run_fem_analysis_native_result({"status": status, "committed": False}, state)
            if result is True:
                violations.append("RUN_FEM_ANALYSIS007 cached success escaped native rejection")
                break
        state = module._NativeMutationState()
        result = module._run_fem_analysis_native_result({"status": "Committed", "committed": True}, state)
        if result is True:
            violations.append("RUN_FEM_ANALYSIS015 commit escaped without a successful postcondition")
    finally:
        sys.modules.pop(module.__name__, None)

    commit_calls = [
        node
        for node in ast.walk(runner)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "commit_native_mutation"
    ]
    if len(commit_calls) != 1:
        violations.append("RUN_FEM_ANALYSIS012 typed path must use exactly one native commit call")
        return violations
    call = commit_calls[0]
    forwarded = call.args[2] if len(call.args) > 2 else None
    if not isinstance(forwarded, ast.Name) or forwarded.id != "native_postcondition":
        violations.append("RUN_FEM_ANALYSIS013 typed path dropped its native postcondition")
    if any(isinstance(node, ast.Name) and node.id == "Any" for node in ast.walk(runner)):
        violations.append("RUN_FEM_ANALYSIS014 typed native path contains Any")
    if any(isinstance(node, ast.Name) and node.id == "Any" for node in ast.walk(native_result)):
        violations.append("RUN_FEM_ANALYSIS014 typed native path contains Any")
    return violations


def _scan_public_adapter(source: str) -> list[str]:
    tree = ast.parse(source, filename=_PUBLIC_ADAPTER)
    operation = _function(tree, "run_fem_analysis_operation")
    calls = set(_called_names(operation))
    violations = []
    if "parse_run_fem_analysis_response" not in calls:
        violations.append("RUN_FEM_ANALYSIS008 public adapter bypasses response validation")
    if {"_run_json_code", "execute_code", "render_template_lines"} & calls:
        violations.append("RUN_FEM_ANALYSIS009 public route returned to generated execution")
    return violations


def _contains_any(node: ast.AST) -> bool:
    return any(isinstance(child, ast.Name) and child.id == "Any" for child in ast.walk(node))


def _scan_typed_surface(root: Path, overrides: Mapping[str, str]) -> list[str]:
    nodes = {
        "leaf": ast.parse(_source(root, _LEAF, overrides)),
        "addon contract": ast.parse(_source(root, _ADDON_CONTRACT, overrides)),
        "client contract": ast.parse(_source(root, _CLIENT_CONTRACT, overrides)),
        "public adapter": _function(
            ast.parse(_source(root, _PUBLIC_ADAPTER, overrides)),
            "run_fem_analysis_operation",
        ),
    }
    return [
        f"RUN_FEM_ANALYSIS014 typed surface contains Any: {name}"
        for name, node in nodes.items()
        if _contains_any(node)
    ]


def scan_run_fem_analysis_architecture(
    root: Path,
    *,
    source_overrides: Mapping[str, str] | None = None,
) -> list[str]:
    overrides = source_overrides or {}
    violations = _scan_leaf(_source(root, _LEAF, overrides))
    violations.extend(_scan_native_release(_source(root, _MUTATION, overrides)))
    violations.extend(_scan_public_adapter(_source(root, _PUBLIC_ADAPTER, overrides)))
    violations.extend(_scan_typed_surface(root, overrides))
    addon_contract = _source(root, _ADDON_CONTRACT, overrides).encode()
    client_contract = _source(root, _CLIENT_CONTRACT, overrides).encode()
    if addon_contract != client_contract:
        violations.append("RUN_FEM_ANALYSIS010 protocol vendors differ")
    if _TEMPLATE and not overrides and (root / _TEMPLATE).exists():
        violations.append("RUN_FEM_ANALYSIS011 generated source template exists")
    return violations


def run_mypy(root: Path) -> int:
    return run_discovered_mypy(root)


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    violations = scan_run_fem_analysis_architecture(root)
    for violation in violations:
        print(violation)
    if violations:
        return 1
    typecheck_result = run_mypy(root)
    if typecheck_result:
        return typecheck_result
    print("run_fem_analysis contract: architecture and static types passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
