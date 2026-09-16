#!/usr/bin/env python3
"""Fast static and architecture gate for the typed ``body_create`` slice."""

from __future__ import annotations

import ast
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from ci.discover_typed_slice import run_discovered_mypy


_BODY_LEAF = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/body_create.py"
_MUTATION = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/body_mutation.py"
_BRIDGE = "addon/FreeCADMCP/collaboration_api.py"
_CAD_DEPS = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/cad_dependencies.py"
_COLLAB_DEPS = "addon/FreeCADMCP/rpc_server/methods/lease_methods_ops/collaboration_dependencies.py"
_PUBLIC_ADAPTER = "src/freecad_mcp/operations/parametric_ops/body_ops.py"
_CLIENT = "src/freecad_mcp/freecad_client_ops/freecad_connection.py"
_ADDON_CONTRACT = "addon/FreeCADMCP/_shared/protocol/body_create_contract.py"
_CLIENT_CONTRACT = "src/freecad_mcp/_shared/protocol/body_create_contract.py"
_TEMPLATE = "src/freecad_mcp/templates/parametric/body_create.py.txt"


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


def _try_function(tree: ast.AST, name: str) -> ast.FunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


_RUN_FORBIDDEN = frozenset(
    {
        "addObject",
        "removeObject",
        "closeDocument",
        "openDocument",
        "newDocument",
        "setActiveDocument",
        "undo",
        "redo",
        "saveAs",
        "restore",
        "execute_code",
        "exec",
        "openTransaction",
        "commitTransaction",
        "abortTransaction",
        "recompute",
        "run_transaction",
    }
)


def _scan_leaf(source: str) -> list[str]:
    tree = ast.parse(source, filename=_BODY_LEAF)
    apply_function = _function(tree, "apply_body_create")
    apply_closure = _class_method(tree, "_BodyCreateExecution", "apply")
    run_function = _class_method(tree, "_BodyCreateExecution", "run")
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
    violations = ["BODY001 leaf owns forbidden execution: " + ", ".join(found)] if found else []
    if "inspect" in _called_names(apply_closure):
        violations.append("BODY002 inspection runs inside apply")
    mutation_calls = [
        node
        for node in ast.walk(run_function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "run_body_native_mutation"
    ]
    if len(mutation_calls) != 1:
        return [*violations, "BODY003 Body must use exactly one typed mutation call"]
    call = mutation_calls[0]
    postcondition = call.args[3] if len(call.args) > 3 else None
    if not (isinstance(postcondition, ast.Attribute) and postcondition.attr == "inspect"):
        violations.append("BODY004 missing typed postcondition=inspect")
    module_run = _try_function(tree, "run_body_create")
    if module_run is not None:
        run_side_effects = sorted(_RUN_FORBIDDEN & set(_called_names(module_run)))
        if run_side_effects:
            violations.append(
                "BODY018 run_body_create owns forbidden CAD side effects: "
                + ", ".join(run_side_effects)
            )
    return violations


def _scan_bridge(source: str) -> list[str]:
    tree = ast.parse(source, filename=_BRIDGE)
    bridge_commit = _class_method(tree, "CollaborationAPI", "commit_body_create_mutation")
    lookup_calls = [
        node
        for node in ast.walk(bridge_commit)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"_document_lookup", "_resolve_admitted_document"}
    ]
    violations = []
    if len(lookup_calls) != 1:
        violations.append("BODY005 bridge must resolve the admitted document exactly once")
    callback_count = _called_names(bridge_commit).count("callback")
    if callback_count != 1 or "_commit_without_native" in _called_names(bridge_commit):
        violations.append("BODY006 postcondition path can reach non-native callback fallback")
    native_calls = [
        node
        for node in ast.walk(bridge_commit)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "commitCompatibilityMutation"
    ]
    if len(native_calls) != 1:
        violations.append("BODY012 typed bridge must use exactly one native commit call")
    else:
        keywords = {item.arg: item.value for item in native_calls[0].keywords}
        structural = keywords.get("structural")
        postcondition = keywords.get("postcondition")
        if not (
            isinstance(structural, ast.Constant)
            and structural.value is True
            and isinstance(postcondition, ast.Name)
            and postcondition.id == "invoke_postcondition"
        ):
            violations.append("BODY013 typed bridge lost its fixed native policy")
    if any(isinstance(node, ast.Name) and node.id == "Any" for node in ast.walk(bridge_commit)):
        violations.append("BODY014 typed native Body bridge contains Any")
    return violations


def _scan_native_release(source: str) -> list[str]:
    tree = ast.parse(source, filename=_MUTATION)
    native_result = _function(tree, "_body_native_result")
    body_runner = _function(tree, "run_body_native_mutation")
    violations = []
    # Execute the small result reducer against adversarial native envelopes.
    # Behavioral sensitivity survives refactoring and checks the actual rejection
    # branch, rather than inferring safety from a variable-name count.
    import types

    module = types.ModuleType("addon.FreeCADMCP.rpc_server.methods.cad_methods_ops._body_gate")
    module.__package__ = "addon.FreeCADMCP.rpc_server.methods.cad_methods_ops"
    sys.modules[module.__name__] = module
    try:
        exec(compile(tree, _MUTATION, "exec"), module.__dict__)
        state = module._NativeBodyMutationState(postcondition_passed=True)
        for status in (
            "Busy",
            "ApplyFailed",
            "PostconditionFailed",
            "PublicationFailed",
            "RollbackFailed",
        ):
            result = module._body_native_result({"status": status, "committed": False}, state)
            if result is True:
                violations.append("BODY007 cached success escaped native rejection")
                break
        state = module._NativeBodyMutationState()
        result = module._body_native_result({"status": "Committed", "committed": True}, state)
        if result is True:
            violations.append("BODY015 commit escaped without a successful postcondition")
    finally:
        sys.modules.pop(module.__name__, None)

    commit_calls = [
        node
        for node in ast.walk(body_runner)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "commit_body_create_mutation"
    ]
    if len(commit_calls) != 1:
        violations.append("BODY012 typed path must use exactly one native commit call")
        return violations
    call = commit_calls[0]
    forwarded = call.args[2] if len(call.args) > 2 else None
    if not isinstance(forwarded, ast.Name) or forwarded.id != "native_postcondition":
        violations.append("BODY013 typed path dropped its native postcondition")

    typed_nodes: list[ast.AST] = [body_runner, native_result]
    for class_node in tree.body:
        if isinstance(class_node, ast.ClassDef) and class_node.name == "_NativeBodyMutationState":
            typed_nodes.append(class_node)
    if any(
        isinstance(node, ast.Name) and node.id == "Any"
        for typed_node in typed_nodes
        for node in ast.walk(typed_node)
    ):
        violations.append("BODY014 typed native Body path contains Any")
    return violations


def _scan_public_adapter(source: str) -> list[str]:
    tree = ast.parse(source, filename=_PUBLIC_ADAPTER)
    operation = _function(tree, "body_create_operation")
    calls = set(_called_names(operation))
    violations = []
    if "parse_body_create_response" not in calls:
        violations.append("BODY008 public adapter bypasses response validation")
    if {"_run_json_code", "execute_code", "render_template_lines"} & calls:
        violations.append("BODY009 public Body route returned to generated execution")
    return violations


def _contains_any(node: ast.AST) -> bool:
    return any(isinstance(child, ast.Name) and child.id == "Any" for child in ast.walk(node))


def _scan_typed_surface(root: Path, overrides: Mapping[str, str]) -> list[str]:
    """Reject explicit ``Any`` only on the complete Body-specific call surface."""

    nodes = {
        "Body leaf": ast.parse(_source(root, _BODY_LEAF, overrides)),
        "addon contract": ast.parse(_source(root, _ADDON_CONTRACT, overrides)),
        "client contract": ast.parse(_source(root, _CLIENT_CONTRACT, overrides)),
        "public adapter": _function(
            ast.parse(_source(root, _PUBLIC_ADAPTER, overrides)),
            "body_create_operation",
        ),
        "RPC client": _class_method(
            ast.parse(_source(root, _CLIENT, overrides)),
            "FreeCADConnection",
            "body_create",
        ),
        "production collaborators": _class_method(
            ast.parse(_source(root, _CAD_DEPS, overrides)),
            "CadCollaborators",
            "commit_body_create_mutation",
        ),
        "native bridge protocol": _class_method(
            ast.parse(_source(root, _COLLAB_DEPS, overrides)),
            "CompatibilityMutationAPI",
            "commit_body_create_mutation",
        ),
    }
    return [
        f"BODY014 typed Body surface contains Any: {name}"
        for name, node in nodes.items()
        if _contains_any(node)
    ]


def scan_body_create_architecture(
    root: Path,
    *,
    source_overrides: Mapping[str, str] | None = None,
) -> list[str]:
    """Return stable violations for the Body-only execution contract."""

    overrides = source_overrides or {}
    violations = _scan_leaf(_source(root, _BODY_LEAF, overrides))
    violations.extend(_scan_bridge(_source(root, _BRIDGE, overrides)))
    violations.extend(_scan_native_release(_source(root, _MUTATION, overrides)))
    violations.extend(_scan_public_adapter(_source(root, _PUBLIC_ADAPTER, overrides)))
    violations.extend(_scan_typed_surface(root, overrides))

    addon_contract = _source(root, _ADDON_CONTRACT, overrides).encode()
    client_contract = _source(root, _CLIENT_CONTRACT, overrides).encode()
    if addon_contract != client_contract:
        violations.append("BODY010 protocol vendors differ")
    if not overrides and (root / _TEMPLATE).exists():
        violations.append("BODY011 generated Body source template exists")
    return violations


def run_mypy(root: Path) -> int:
    # Static pyproject globs and import-following overrides gate the typed slice.
    return run_discovered_mypy(root)


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    violations = scan_body_create_architecture(root)
    for violation in violations:
        print(violation)
    if violations:
        return 1
    typecheck_result = run_mypy(root)
    if typecheck_result:
        return typecheck_result
    print("body_create contract: architecture and static types passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
