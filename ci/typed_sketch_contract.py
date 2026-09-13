"""Architecture gate shared by typed sketch execute-code operations."""

from __future__ import annotations

import ast
import sys
import types
from collections.abc import Mapping
from pathlib import Path

from ci.typed_sketch_ops import SKETCH_OP_BY_NAME, SketchOpSpec

_BRIDGE = "addon/FreeCADMCP/collaboration_api.py"
_CAD_DEPS = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/cad_dependencies.py"
_COLLAB_DEPS = "addon/FreeCADMCP/rpc_server/methods/lease_methods_ops/collaboration_dependencies.py"
_CLIENT = "src/freecad_mcp/freecad_client_ops/freecad_connection.py"


def _leaf_path(op: str) -> str:
    return f"addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/{op}.py"


def _mutation_path(op: str) -> str:
    return f"addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/{op}_mutation.py"


def _public_path(op: str) -> str:
    return f"src/freecad_mcp/operations/parametric_ops/{op}.py"


def _addon_contract_path(op: str) -> str:
    return f"addon/FreeCADMCP/_shared/protocol/{op}_contract.py"


def _client_contract_path(op: str) -> str:
    return f"src/freecad_mcp/_shared/protocol/{op}_contract.py"


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


def _contains_any(node: ast.AST) -> bool:
    return any(isinstance(child, ast.Name) and child.id == "Any" for child in ast.walk(node))


def _prefix(spec: SketchOpSpec) -> str:
    return spec["upper"]


def _scan_leaf(source: str, spec: SketchOpSpec) -> list[str]:
    op = spec["name"]
    pascal = spec["pascal"]
    prefix = _prefix(spec)
    apply_name = f"apply_{op}"
    run_mutation = f"run_{op}_native_mutation"
    tree = ast.parse(source, filename=_leaf_path(op))
    apply_function = _function(tree, apply_name)
    apply_closure = _class_method(tree, f"_{pascal}Execution", "apply")
    run_function = _class_method(tree, f"_{pascal}Execution", "run")
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
    violations = [f"{prefix}001 leaf owns forbidden execution: " + ", ".join(found)] if found else []
    if "inspect" in _called_names(apply_closure):
        violations.append(f"{prefix}002 inspection runs inside apply")
    mutation_calls = [
        node
        for node in ast.walk(run_function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == run_mutation
    ]
    if len(mutation_calls) != 1:
        return [*violations, f"{prefix}003 {op} must use exactly one typed mutation call"]
    call = mutation_calls[0]
    postcondition = call.args[3] if len(call.args) > 3 else None
    if not (isinstance(postcondition, ast.Attribute) and postcondition.attr == "inspect"):
        violations.append(f"{prefix}004 missing typed postcondition=inspect")
    return violations


def _scan_bridge(source: str, spec: SketchOpSpec) -> list[str]:
    prefix = _prefix(spec)
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
        violations.append(f"{prefix}005 bridge must resolve the admitted document exactly once")
    callback_count = _called_names(bridge_commit).count("callback")
    if callback_count != 1 or "_commit_without_native" in _called_names(bridge_commit):
        violations.append(f"{prefix}006 postcondition path can reach non-native callback fallback")
    native_calls = [
        node
        for node in ast.walk(bridge_commit)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "commitCompatibilityMutation"
    ]
    if len(native_calls) != 1:
        violations.append(f"{prefix}012 typed bridge must use exactly one native commit call")
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
            violations.append(f"{prefix}013 typed bridge lost its fixed native policy")
    if any(isinstance(node, ast.Name) and node.id == "Any" for node in ast.walk(bridge_commit)):
        violations.append(f"{prefix}014 typed native sketch bridge contains Any")
    return violations


def _scan_native_release(source: str, spec: SketchOpSpec) -> list[str]:
    op = spec["name"]
    prefix = _prefix(spec)
    mutation_rel = _mutation_path(op)
    tree = ast.parse(source, filename=mutation_rel)
    result_name = f"_{op}_native_result"
    runner_name = f"run_{op}_native_mutation"
    state_name = f"_Native{spec['pascal']}MutationState"
    native_result = _function(tree, result_name)
    body_runner = _function(tree, runner_name)
    violations = []
    module = types.ModuleType(
        "addon.FreeCADMCP.rpc_server.methods.cad_methods_ops._sketch_exec_gate"
    )
    module.__package__ = "addon.FreeCADMCP.rpc_server.methods.cad_methods_ops"
    sys.modules[module.__name__] = module
    try:
        exec(compile(tree, mutation_rel, "exec"), module.__dict__)
        state_cls = getattr(module, state_name)
        reducer = getattr(module, result_name)
        state = state_cls(postcondition_passed=True)
        for status in (
            "Busy",
            "ApplyFailed",
            "PostconditionFailed",
            "PublicationFailed",
            "RollbackFailed",
        ):
            result = reducer({"status": status, "committed": False}, state)
            if result is True:
                violations.append(f"{prefix}007 cached success escaped native rejection")
                break
        state = state_cls()
        result = reducer({"status": "Committed", "committed": True}, state)
        if result is True:
            violations.append(f"{prefix}015 commit escaped without a successful postcondition")
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
        violations.append(f"{prefix}012 typed path must use exactly one native commit call")
        return violations
    call = commit_calls[0]
    forwarded = call.args[2] if len(call.args) > 2 else None
    if not isinstance(forwarded, ast.Name) or forwarded.id != "native_postcondition":
        violations.append(f"{prefix}013 typed path dropped its native postcondition")

    typed_nodes: list[ast.AST] = [body_runner, native_result]
    for class_node in tree.body:
        if isinstance(class_node, ast.ClassDef) and class_node.name == state_name:
            typed_nodes.append(class_node)
    if any(
        isinstance(node, ast.Name) and node.id == "Any"
        for typed_node in typed_nodes
        for node in ast.walk(typed_node)
    ):
        violations.append(f"{prefix}014 typed native sketch path contains Any")
    return violations


def _scan_public_adapter(source: str, spec: SketchOpSpec) -> list[str]:
    op = spec["name"]
    prefix = _prefix(spec)
    tree = ast.parse(source, filename=_public_path(op))
    operation = _function(tree, f"{op}_operation")
    calls = set(_called_names(operation))
    violations = []
    if f"parse_{op}_response" not in calls:
        violations.append(f"{prefix}008 public adapter bypasses response validation")
    if {"_run_json_code", "execute_code", "render_template_lines"} & calls:
        violations.append(f"{prefix}009 public sketch route returned to generated execution")
    return violations


def _scan_typed_surface(root: Path, spec: SketchOpSpec, overrides: Mapping[str, str]) -> list[str]:
    op = spec["name"]
    prefix = _prefix(spec)
    nodes = {
        "sketch leaf": ast.parse(_source(root, _leaf_path(op), overrides)),
        "addon contract": ast.parse(_source(root, _addon_contract_path(op), overrides)),
        "client contract": ast.parse(_source(root, _client_contract_path(op), overrides)),
        "public adapter": _function(
            ast.parse(_source(root, _public_path(op), overrides)),
            f"{op}_operation",
        ),
        "RPC client": _class_method(
            ast.parse(_source(root, _CLIENT, overrides)),
            "FreeCADConnection",
            op,
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
        f"{prefix}014 typed sketch surface contains Any: {name}"
        for name, node in nodes.items()
        if _contains_any(node)
    ]


def scan_sketch_op_architecture(
    root: Path,
    op: str,
    *,
    source_overrides: Mapping[str, str] | None = None,
) -> list[str]:
    """Return stable violations for one typed sketch operation."""

    spec = SKETCH_OP_BY_NAME[op]
    overrides = source_overrides or {}
    violations = _scan_leaf(_source(root, _leaf_path(op), overrides), spec)
    violations.extend(_scan_bridge(_source(root, _BRIDGE, overrides), spec))
    violations.extend(_scan_native_release(_source(root, _mutation_path(op), overrides), spec))
    violations.extend(_scan_public_adapter(_source(root, _public_path(op), overrides), spec))
    violations.extend(_scan_typed_surface(root, spec, overrides))

    addon_contract = _source(root, _addon_contract_path(op), overrides).encode()
    client_contract = _source(root, _client_contract_path(op), overrides).encode()
    prefix = _prefix(spec)
    if addon_contract != client_contract:
        violations.append(f"{prefix}010 protocol vendors differ")
    if not overrides and (root / spec["template"]).exists():
        violations.append(f"{prefix}011 generated sketch source template exists")
    return violations


def main_for_op(op: str) -> int:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    violations = scan_sketch_op_architecture(root, op)
    for violation in violations:
        print(violation)
    if violations:
        return 1
    print(f"{op} contract: architecture passed")
    return 0
