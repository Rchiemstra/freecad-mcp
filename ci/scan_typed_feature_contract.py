"""Architecture gate shared by typed G-features-p3 contract scripts."""

from __future__ import annotations

import ast
import sys
import types
from collections.abc import Mapping, Sequence
from pathlib import Path

from ci.discover_typed_slice import run_discovered_mypy


def pascal(op: str) -> str:
    return "".join(part.title() for part in op.split("_"))


def prefix(op: str) -> str:
    return op.upper()


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


_WRITE_LIKE = frozenset(
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

_RUN_FORBIDDEN = _WRITE_LIKE

_GENERATED_EXECUTION = frozenset(
    {"_run_json_code", "execute_code", "render_template_lines", "_run_code"}
)


def _try_function(tree: ast.AST, name: str) -> ast.FunctionDef | None:
    try:
        return _function(tree, name)
    except ValueError:
        return None


def _paths(op: str) -> dict[str, str]:
    return {
        "leaf": f"addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/{op}.py",
        "mutation": f"addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/{op}_mutation.py",
        "bridge": "addon/FreeCADMCP/collaboration_api.py",
        "cad_deps": "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/cad_dependencies.py",
        "collab_deps": (
            "addon/FreeCADMCP/rpc_server/methods/lease_methods_ops/collaboration_dependencies.py"
        ),
        "public": f"src/freecad_mcp/operations/parametric_ops/{op}.py",
        "client": "src/freecad_mcp/freecad_client_ops/freecad_connection.py",
        "addon_contract": f"addon/FreeCADMCP/_shared/protocol/{op}_contract.py",
        "client_contract": f"src/freecad_mcp/_shared/protocol/{op}_contract.py",
    }


def _scan_leaf(op: str, source: str) -> list[str]:
    paths = _paths(op)
    code = prefix(op)
    tree = ast.parse(source, filename=paths["leaf"])
    apply_function = _function(tree, f"apply_{op}")
    apply_closure = _class_method(tree, f"_{pascal(op)}Execution", "apply")
    run_function = _class_method(tree, f"_{pascal(op)}Execution", "run")
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
    violations = (
        [f"{code}001 leaf owns forbidden execution: " + ", ".join(found)] if found else []
    )
    if "inspect" in _called_names(apply_closure):
        violations.append(f"{code}002 inspection runs inside apply")
    mutation_calls = [
        node
        for node in ast.walk(run_function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == f"run_{op}_native_mutation"
    ]
    if len(mutation_calls) != 1:
        return [*violations, f"{code}003 {op} must use exactly one typed mutation call"]
    call = mutation_calls[0]
    postcondition = call.args[3] if len(call.args) > 3 else None
    if not (isinstance(postcondition, ast.Attribute) and postcondition.attr == "inspect"):
        violations.append(f"{code}004 missing typed postcondition=inspect")

    module_run = _try_function(tree, f"run_{op}")
    if module_run is not None:
        run_side_effects = sorted(_RUN_FORBIDDEN & set(_called_names(module_run)))
        if run_side_effects:
            violations.append(
                f"{code}018 run_{op} owns forbidden CAD side effects: "
                + ", ".join(run_side_effects)
            )

    inspect_closure = None
    try:
        inspect_closure = _class_method(tree, f"_{pascal(op)}Execution", "inspect")
    except ValueError:
        inspect_closure = None
    inspect_method = _try_function(tree, f"read_{op}_result")
    for label, node in (
        ("inspect", inspect_closure),
        (f"read_{op}_result", inspect_method),
    ):
        if node is None:
            continue
        write_calls = sorted(_WRITE_LIKE & set(_called_names(node)))
        if write_calls:
            violations.append(
                f"{code}019 {label} path performs writes: " + ", ".join(write_calls)
            )

    apply_writes = _WRITE_LIKE & set(_called_names(apply_function))
    if module_run is not None and not apply_writes:
        run_side_effects = sorted(_RUN_FORBIDDEN & set(_called_names(module_run)))
        if run_side_effects:
            violations.append(f"{code}020 identity apply with post-run CAD side effects")

    if _GENERATED_EXECUTION & set(_called_names(tree)):
        violations.append(f"{code}009 public {op} route returned to generated execution")

    handler = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "TYPED_RPC_HANDLER":
                    handler = node.value
    if not (
        isinstance(handler, ast.Tuple)
        and len(handler.elts) == 2
        and isinstance(handler.elts[0], ast.Constant)
        and handler.elts[0].value == op
    ):
        violations.append(f"{code}016 missing TYPED_RPC_HANDLER for {op}")
    return violations


def _scan_bridge(op: str, source: str) -> list[str]:
    paths = _paths(op)
    code = prefix(op)
    tree = ast.parse(source, filename=paths["bridge"])
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
        violations.append(f"{code}005 bridge must resolve the admitted document exactly once")
    callback_count = _called_names(bridge_commit).count("callback")
    if callback_count != 1 or "_commit_without_native" in _called_names(bridge_commit):
        violations.append(f"{code}006 postcondition path can reach non-native callback fallback")
    native_calls = [
        node
        for node in ast.walk(bridge_commit)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "commitCompatibilityMutation"
    ]
    if len(native_calls) != 1:
        violations.append(f"{code}012 typed bridge must use exactly one native commit call")
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
            violations.append(f"{code}013 typed bridge lost its fixed native policy")
    if any(isinstance(node, ast.Name) and node.id == "Any" for node in ast.walk(bridge_commit)):
        violations.append(f"{code}014 typed native {op} bridge contains Any")
    return violations


def _mutation_state_class_name(tree: ast.Module, result_name: str, op: str) -> str:
    native_result = _function(tree, result_name)
    for child in ast.walk(native_result):
        if not isinstance(child, ast.arg) or child.annotation is None:
            continue
        if isinstance(child.annotation, ast.Name) and child.annotation.id.endswith("MutationState"):
            return child.annotation.id
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name.endswith("MutationState"):
            return node.name
    return f"_{pascal(op)}NativeMutationState"


def _scan_native_release(op: str, source: str) -> list[str]:
    paths = _paths(op)
    code = prefix(op)
    tree = ast.parse(source, filename=paths["mutation"])
    native_result = _function(tree, f"_{op}_native_result")
    runner = _function(tree, f"run_{op}_native_mutation")
    violations: list[str] = []
    result_name = f"_{op}_native_result"
    state_name = _mutation_state_class_name(tree, result_name, op)
    module = types.ModuleType(
        f"addon.FreeCADMCP.rpc_server.methods.cad_methods_ops._{op}_gate"
    )
    module.__package__ = "addon.FreeCADMCP.rpc_server.methods.cad_methods_ops"
    sys.modules[module.__name__] = module
    try:
        exec(compile(tree, paths["mutation"], "exec"), module.__dict__)
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
                violations.append(f"{code}007 cached success escaped native rejection")
                break
        state = state_cls()
        result = reducer({"status": "Committed", "committed": True}, state)
        if result is True:
            violations.append(f"{code}015 commit escaped without a successful postcondition")
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
        violations.append(f"{code}012 typed path must use exactly one native commit call")
        return violations
    call = commit_calls[0]
    forwarded = call.args[2] if len(call.args) > 2 else None
    if not isinstance(forwarded, ast.Name) or forwarded.id != "native_postcondition":
        violations.append(f"{code}013 typed path dropped its native postcondition")

    typed_nodes: list[ast.AST] = [runner, native_result]
    for class_node in tree.body:
        if isinstance(class_node, ast.ClassDef) and class_node.name == state_name:
            typed_nodes.append(class_node)
    if any(
        isinstance(node, ast.Name) and node.id == "Any"
        for typed_node in typed_nodes
        for node in ast.walk(typed_node)
    ):
        violations.append(f"{code}014 typed native {op} path contains Any")
    return violations


def _scan_public_adapter(
    op: str,
    source: str,
    *,
    include_freecad_call: bool = True,
) -> list[str]:
    paths = _paths(op)
    code = prefix(op)
    tree = ast.parse(source, filename=paths["public"])
    operation = _function(tree, f"{op}_operation")
    calls = set(_called_names(operation))
    violations = []
    if f"parse_{op}_response" not in calls:
        violations.append(f"{code}008 public adapter bypasses response validation")
    if {"_run_json_code", "execute_code", "render_template_lines", "_run_code"} & calls:
        violations.append(f"{code}009 public {op} route returned to generated execution")
    if include_freecad_call and op not in calls:
        violations.append(f"{code}017 public adapter does not call freecad.{op}()")
    return violations


def _scan_typed_surface(op: str, root: Path, overrides: Mapping[str, str]) -> list[str]:
    paths = _paths(op)
    code = prefix(op)
    nodes = {
        f"{op} leaf": ast.parse(_source(root, paths["leaf"], overrides)),
        "addon contract": ast.parse(_source(root, paths["addon_contract"], overrides)),
        "client contract": ast.parse(_source(root, paths["client_contract"], overrides)),
        "public adapter": _function(
            ast.parse(_source(root, paths["public"], overrides)),
            f"{op}_operation",
        ),
        "RPC client": _class_method(
            ast.parse(_source(root, paths["client"], overrides)),
            "FreeCADConnection",
            op,
        ),
        "production collaborators": _class_method(
            ast.parse(_source(root, paths["cad_deps"], overrides)),
            "CadCollaborators",
            "commit_native_mutation",
        ),
        "native bridge protocol": _class_method(
            ast.parse(_source(root, paths["collab_deps"], overrides)),
            "CompatibilityMutationAPI",
            "commit_native_mutation",
        ),
    }
    return [
        f"{code}014 typed {op} surface contains Any: {name}"
        for name, node in nodes.items()
        if _contains_any(node)
    ]


def scan_feature_architecture(
    root: Path,
    op: str,
    *,
    source_overrides: Mapping[str, str] | None = None,
) -> list[str]:
    """Return stable violations for one typed feature mutation."""

    overrides = source_overrides or {}
    paths = _paths(op)
    code = prefix(op)
    violations = _scan_leaf(op, _source(root, paths["leaf"], overrides))
    violations.extend(_scan_bridge(op, _source(root, paths["bridge"], overrides)))
    violations.extend(_scan_native_release(op, _source(root, paths["mutation"], overrides)))
    violations.extend(_scan_public_adapter(op, _source(root, paths["public"], overrides)))
    violations.extend(_scan_typed_surface(op, root, overrides))

    addon_contract = _source(root, paths["addon_contract"], overrides).encode()
    client_contract = _source(root, paths["client_contract"], overrides).encode()
    if addon_contract != client_contract:
        violations.append(f"{code}010 protocol vendors differ")
    return violations


def main_for_op(op: str, argv: Sequence[str] | None = None, *, typecheck: bool = True) -> int:
    del argv
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from ci.scan_execution_policy_gates import scan_op_architecture

    violations = scan_op_architecture(root, op)
    for violation in violations:
        print(violation)
    if violations:
        return 1
    if typecheck:
        typecheck_result = run_discovered_mypy(root)
        if typecheck_result:
            return typecheck_result
        print(f"{op} contract: architecture and static types passed")
        return 0
    print(f"{op} contract: architecture passed")
    return 0
