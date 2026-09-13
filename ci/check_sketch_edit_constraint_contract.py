#!/usr/bin/env python3
"""Fast static and architecture gate for the typed ``sketch_edit_constraint`` slice."""

from __future__ import annotations

import ast
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from ci.discover_typed_slice import run_discovered_mypy


_LEAF = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/sketch_edit_constraint.py"
_MUTATION = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/sketch_edit_constraint_mutation.py"
_BRIDGE = "addon/FreeCADMCP/collaboration_api.py"
_CAD_DEPS = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/cad_dependencies.py"
_COLLAB_DEPS = "addon/FreeCADMCP/rpc_server/methods/lease_methods_ops/collaboration_dependencies.py"
_PUBLIC_ADAPTER = "src/freecad_mcp/operations/parametric_ops/sketch_edit_constraint.py"
_CLIENT = "src/freecad_mcp/freecad_client_ops/freecad_connection.py"
_ADDON_CONTRACT = "addon/FreeCADMCP/_shared/protocol/sketch_edit_constraint_contract.py"
_CLIENT_CONTRACT = "src/freecad_mcp/_shared/protocol/sketch_edit_constraint_contract.py"


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
    apply_function = _function(tree, "apply_sketch_edit_constraint")
    apply_closure = _class_method(tree, "_SketchEditConstraintExecution", "apply")
    run_function = _class_method(tree, "_SketchEditConstraintExecution", "run")
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
    violations = ["SKET001 leaf owns forbidden execution: " + ", ".join(found)] if found else []
    if "inspect" in _called_names(apply_closure):
        violations.append("SKET002 inspection runs inside apply")
    mutation_calls = [
        node
        for node in ast.walk(run_function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "run_sketch_edit_constraint_native_mutation"
    ]
    if len(mutation_calls) != 1:
        return [*violations, "SKET003 sketch_edit_constraint must use exactly one typed mutation call"]
    call = mutation_calls[0]
    postcondition = call.args[3] if len(call.args) > 3 else None
    if not (isinstance(postcondition, ast.Attribute) and postcondition.attr == "inspect"):
        violations.append("SKET004 missing typed postcondition=inspect")
    return violations


def _scan_bridge(source: str) -> list[str]:
    tree = ast.parse(source, filename=_BRIDGE)
    bridge_commit = _class_method(tree, "CollaborationAPI", "commit_native_mutation")
    lookup_calls = [
        node
        for node in ast.walk(bridge_commit)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"_document_lookup", "_resolve_admitted_document"}
    ]
    violations = []
    if len(lookup_calls) != 1:
        violations.append("SKET005 bridge must resolve the admitted document exactly once")
    callback_count = _called_names(bridge_commit).count("callback")
    if callback_count != 1 or "_commit_without_native" in _called_names(bridge_commit):
        violations.append("SKET006 postcondition path can reach non-native callback fallback")
    native_calls = [
        node
        for node in ast.walk(bridge_commit)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "commitCompatibilityMutation"
    ]
    if len(native_calls) != 1:
        violations.append("SKET012 typed bridge must use exactly one native commit call")
    else:
        keywords = {item.arg: item.value for item in native_calls[0].keywords}
        structural = keywords.get("structural")
        postcondition = keywords.get("postcondition")
        if not (
            isinstance(structural, ast.Name)
            and structural.id == "structural"
            and isinstance(postcondition, ast.Name)
            and postcondition.id == "invoke_postcondition"
        ):
            violations.append("SKET013 typed bridge lost its fixed native policy")
    if any(isinstance(node, ast.Name) and node.id == "Any" for node in ast.walk(bridge_commit)):
        violations.append("SKET014 typed native sketch_edit_constraint bridge contains Any")
    return violations


def _scan_native_release(source: str) -> list[str]:
    tree = ast.parse(source, filename=_MUTATION)
    native_result = _function(tree, "_sketch_edit_constraint_native_result")
    body_runner = _function(tree, "run_sketch_edit_constraint_native_mutation")
    violations = []
    import types

    module = types.ModuleType("addon.FreeCADMCP.rpc_server.methods.cad_methods_ops._sketch_edit_constraint_gate")
    module.__package__ = "addon.FreeCADMCP.rpc_server.methods.cad_methods_ops"
    sys.modules[module.__name__] = module
    try:
        exec(compile(tree, _MUTATION, "exec"), module.__dict__)
        state = module._NativeSketchEditConstraintMutationState(postcondition_passed=True)
        for status in (
            "Busy",
            "ApplyFailed",
            "PostconditionFailed",
            "PublicationFailed",
            "RollbackFailed",
        ):
            result = module._sketch_edit_constraint_native_result({"status": status, "committed": False}, state)
            if result is True:
                violations.append("SKET007 cached success escaped native rejection")
                break
        state = module._NativeSketchEditConstraintMutationState()
        result = module._sketch_edit_constraint_native_result({"status": "Committed", "committed": True}, state)
        if result is True:
            violations.append("SKET015 commit escaped without a successful postcondition")
    finally:
        sys.modules.pop(module.__name__, None)

    commit_calls = [
        node
        for node in ast.walk(body_runner)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "commit_native_mutation"
    ]
    if len(commit_calls) != 1:
        violations.append("SKET012 typed path must use exactly one native commit call")
        return violations
    call = commit_calls[0]
    forwarded = call.args[2] if len(call.args) > 2 else None
    if not isinstance(forwarded, ast.Name) or forwarded.id != "native_postcondition":
        violations.append("SKET013 typed path dropped its native postcondition")
    if any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr.startswith("commit_")
        and node.func.attr.endswith("_mutation")
        and node.func.attr != "commit_native_mutation"
        for node in ast.walk(body_runner)
    ):
        violations.append("SKET012 typed path must not call a per-op commit method")

    typed_nodes: list[ast.AST] = [body_runner, native_result]
    for class_node in tree.body:
        if isinstance(class_node, ast.ClassDef) and class_node.name == "_NativeSketchEditConstraintMutationState":
            typed_nodes.append(class_node)
    if any(
        isinstance(node, ast.Name) and node.id == "Any"
        for typed_node in typed_nodes
        for node in ast.walk(typed_node)
    ):
        violations.append("SKET014 typed native sketch_edit_constraint path contains Any")
    return violations


def _scan_public_adapter(source: str) -> list[str]:
    tree = ast.parse(source, filename=_PUBLIC_ADAPTER)
    operation = _function(tree, "sketch_edit_constraint_operation")
    calls = set(_called_names(operation))
    violations = []
    if "parse_sketch_edit_constraint_response" not in calls:
        violations.append("SKET008 public adapter bypasses response validation")
    if {"_run_json_code", "execute_code", "render_template_lines"} & calls:
        violations.append("SKET009 public sketch_edit_constraint route returned to generated execution")
    return violations


def _contains_any(node: ast.AST) -> bool:
    return any(isinstance(child, ast.Name) and child.id == "Any" for child in ast.walk(node))


def _scan_typed_surface(root: Path, overrides: Mapping[str, str]) -> list[str]:
    nodes = {
        "SketchEditConstraint leaf": ast.parse(_source(root, _LEAF, overrides)),
        "addon contract": ast.parse(_source(root, _ADDON_CONTRACT, overrides)),
        "client contract": ast.parse(_source(root, _CLIENT_CONTRACT, overrides)),
        "public adapter": _function(
            ast.parse(_source(root, _PUBLIC_ADAPTER, overrides)),
            "sketch_edit_constraint_operation",
        ),
        "RPC client": _class_method(
            ast.parse(_source(root, _CLIENT, overrides)),
            "FreeCADConnection",
            "sketch_edit_constraint",
        ),
        "production collaborators": _class_method(
            ast.parse(_source(root, _CAD_DEPS, overrides)),
            "CadCollaborators",
            "commit_native_mutation",
        ),
        "native bridge protocol": _class_method(
            ast.parse(_source(root, _COLLAB_DEPS, overrides)),
            "CompatibilityMutationAPI",
            "commit_native_mutation",
        ),
    }
    return [
        f"SKET014 typed SketchEditConstraint surface contains Any: {name}"
        for name, node in nodes.items()
        if _contains_any(node)
    ]


def scan_sketch_edit_constraint_architecture(
    root: Path,
    *,
    source_overrides: Mapping[str, str] | None = None,
) -> list[str]:
    """Return stable violations for the sketch_edit_constraint execution contract."""

    overrides = source_overrides or {}
    violations = _scan_leaf(_source(root, _LEAF, overrides))
    violations.extend(_scan_bridge(_source(root, _BRIDGE, overrides)))
    violations.extend(_scan_native_release(_source(root, _MUTATION, overrides)))
    violations.extend(_scan_public_adapter(_source(root, _PUBLIC_ADAPTER, overrides)))
    violations.extend(_scan_typed_surface(root, overrides))

    addon_contract = _source(root, _ADDON_CONTRACT, overrides).encode()
    client_contract = _source(root, _CLIENT_CONTRACT, overrides).encode()
    if addon_contract != client_contract:
        violations.append("SKET010 protocol vendors differ")
    return violations


def run_mypy(root: Path) -> int:
    return run_discovered_mypy(root)


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    violations = scan_sketch_edit_constraint_architecture(root)
    for violation in violations:
        print(violation)
    if violations:
        return 1
    typecheck_result = run_mypy(root)
    if typecheck_result:
        return typecheck_result
    print("sketch_edit_constraint contract: architecture and static types passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
