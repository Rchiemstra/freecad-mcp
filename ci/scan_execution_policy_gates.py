"""Policy-specific architecture scanners for typed CAD RPC handlers."""

from __future__ import annotations

import ast
import importlib.util
import re
from collections.abc import Callable, Mapping
from enum import Enum
from pathlib import Path
from typing import Protocol

from ci.scan_typed_feature_contract import (
    _called_names,
    _class_method,
    _contains_any,
    _function,
    _paths,
    _scan_public_adapter,
    _source,
    pascal,
    prefix,
    scan_feature_architecture,
)

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

_LIFECYCLE_APIS = frozenset({"closeDocument", "openDocument", "newDocument", "setActiveDocument"})

_HISTORY_APIS = frozenset({"undo", "redo"})

_LIFECYCLE_OUTCOMES = frozenset({"prepared", "performed", "verified", "compensated", "uncertain"})

_MUTATION_PIPELINE_ATTRS = frozenset(
    {"commit_native_mutation", "commitCompatibilityMutation", "commit_body_create_mutation"}
)

_GENERATED_EXECUTION = frozenset(
    {"_run_json_code", "execute_code", "render_template_lines", "_run_code"}
)

_EXTERNAL_APPLY_MARKERS = (
    "measure_io_actions.export_",
    "measure_io_actions.export_step",
    "measure_io_actions.export_stl",
    "measure_io_actions.export_brep",
    "create_mesh",
    "GmshTools",
    ".invoke(",
)


class _ExecutionPolicy(str, Enum):
    DOCUMENT_MUTATION = "document_mutation"
    DOCUMENT_QUERY = "document_query"
    DOCUMENT_LIFECYCLE = "document_lifecycle"
    HISTORY_OPERATION = "history_operation"
    EXTERNAL_EFFECT = "external_effect"
    GUI_GLOBAL = "gui_global"


def _load_addon_execution_policies(root: Path) -> dict[str, str]:
    path = root / "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/execution_policies.py"
    spec = importlib.util.spec_from_file_location("addon_execution_policies_gate", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load addon execution policies from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    policies = getattr(module, "EXECUTION_POLICIES")
    return {name: policy.value for name, policy in policies.items()}


def _parse_policy_tuples(root: Path) -> dict[str, str]:
    path = root / "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/execution_policies.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    tuple_names: dict[str, tuple[str, ...]] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Tuple):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name) or not target.id.startswith("_"):
                continue
            names = tuple(
                elt.value
                for elt in node.value.elts
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
            )
            if names:
                tuple_names[target.id] = names
    mapping = {
        "_DOCUMENT_LIFECYCLE": _ExecutionPolicy.DOCUMENT_LIFECYCLE.value,
        "_HISTORY_OPERATION": _ExecutionPolicy.HISTORY_OPERATION.value,
        "_EXTERNAL_EFFECT": _ExecutionPolicy.EXTERNAL_EFFECT.value,
        "_GUI_GLOBAL": _ExecutionPolicy.GUI_GLOBAL.value,
        "_DOCUMENT_QUERY": _ExecutionPolicy.DOCUMENT_QUERY.value,
        "_DOCUMENT_MUTATION": _ExecutionPolicy.DOCUMENT_MUTATION.value,
    }
    policies: dict[str, str] = {}
    for tuple_name, policy_value in mapping.items():
        for op in tuple_names.get(tuple_name, ()):
            policies[op] = policy_value
    return policies


def policy_for_op(root: Path, op: str) -> str:
    try:
        return _load_addon_execution_policies(root)[op]
    except Exception:
        policies = _parse_policy_tuples(root)
        try:
            return policies[op]
        except KeyError as exc:
            raise KeyError(f"no execution policy registered for {op!r}") from exc


def _try_function(tree: ast.AST, name: str) -> ast.FunctionDef | None:
    try:
        return _function(tree, name)
    except ValueError:
        return None


def _try_read_source(root: Path, relative: str, overrides: Mapping[str, str]) -> str | None:
    if relative in overrides:
        return overrides[relative]
    path = root / relative
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def _leaf_tree(root: Path, op: str, overrides: Mapping[str, str]) -> ast.Module | None:
    paths = _paths(op)
    source = _try_read_source(root, paths["leaf"], overrides)
    if source is None:
        return None
    return ast.parse(source, filename=paths["leaf"])


def _mutation_tree(root: Path, op: str, overrides: Mapping[str, str]) -> ast.Module | None:
    paths = _paths(op)
    source = _try_read_source(root, paths["mutation"], overrides)
    if source is None:
        return None
    return ast.parse(source, filename=paths["mutation"])


def _contract_source(root: Path, op: str, overrides: Mapping[str, str]) -> str | None:
    paths = _paths(op)
    return _try_read_source(root, paths["addon_contract"], overrides)


def _uses_mutation_pipeline(node: ast.AST, op: str) -> list[str]:
    hits: list[str] = []
    native_runner = f"run_{op}_native_mutation"
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if isinstance(child.func, ast.Name) and child.func.id == native_runner:
            hits.append(native_runner)
        elif isinstance(child.func, ast.Attribute) and child.func.attr in _MUTATION_PIPELINE_ATTRS:
            hits.append(child.func.attr)
    return hits


def _lifecycle_api_mentions(node: ast.AST) -> list[str]:
    found = set(_LIFECYCLE_APIS & set(_called_names(node)))
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            if child.value in _LIFECYCLE_APIS:
                found.add(child.value)
    return sorted(found)


def _history_perform_locations(source: str, op: str) -> tuple[bool, bool]:
    tree = ast.parse(source)

    def _performs_history(fn: ast.FunctionDef | None, api: str) -> bool:
        if fn is None:
            return False
        text = ast.unparse(fn)
        has_api_ref = f'"{api}"' in text or f"'{api}'" in text
        invokes = "action()" in text or f".{api}(" in text
        return has_api_ref and invokes

    api = "undo" if op == "undo" else "redo"
    apply_fn = _try_function(tree, f"apply_{op}")
    run_fn = _try_function(tree, f"run_{op}")
    return _performs_history(apply_fn, api), _performs_history(run_fn, api)


def _contract_uses_committed_outcome(contract_source: str) -> bool:
    if 'outcome: Literal["committed"]' in contract_source:
        return True
    if "committed: Literal[True]" in contract_source and "Success" in contract_source:
        return True
    return bool(re.search(r'outcome:\s*Literal\[\s*"committed"\s*\]', contract_source))


def _scan_leaf_generated_execution(op: str, tree: ast.Module) -> list[str]:
    code = prefix(op)
    calls = set(_called_names(tree))
    if _GENERATED_EXECUTION & calls:
        return [f"{code}009 public {op} route returned to generated execution"]
    return []


def _scan_protocol_vendors(op: str, root: Path, overrides: Mapping[str, str]) -> list[str]:
    paths = _paths(op)
    code = prefix(op)
    addon = _try_read_source(root, paths["addon_contract"], overrides)
    client = _try_read_source(root, paths["client_contract"], overrides)
    if addon is None or client is None:
        return []
    if addon.encode() != client.encode():
        return [f"{code}010 protocol vendors differ"]
    return []


def _scan_typed_surface_any(op: str, root: Path, overrides: Mapping[str, str]) -> list[str]:
    paths = _paths(op)
    code = prefix(op)
    violations: list[str] = []
    leaf_source = _try_read_source(root, paths["leaf"], overrides)
    if leaf_source is not None:
        leaf_tree = ast.parse(leaf_source, filename=paths["leaf"])
        if _contains_any(leaf_tree):
            violations.append(f"{code}014 typed {op} surface contains Any: {op} leaf")
    for label, relative, parser in (
        ("addon contract", paths["addon_contract"], ast.parse),
        ("client contract", paths["client_contract"], ast.parse),
    ):
        source = _try_read_source(root, relative, overrides)
        if source is None:
            continue
        node = parser(source, filename=relative)
        if _contains_any(node):
            violations.append(f"{code}014 typed {op} surface contains Any: {label}")
    public_source = _try_read_source(root, paths["public"], overrides)
    if public_source is not None:
        public_tree = ast.parse(public_source, filename=paths["public"])
        operation = _try_function(public_tree, f"{op}_operation")
        if operation is not None and _contains_any(operation):
            violations.append(f"{code}014 typed {op} surface contains Any: public adapter")
    client_source = _try_read_source(root, paths["client"], overrides)
    if client_source is not None:
        client_tree = ast.parse(client_source, filename=paths["client"])
        try:
            rpc_method = _class_method(client_tree, "FreeCADConnection", op)
        except ValueError:
            rpc_method = None
        if rpc_method is not None and _contains_any(rpc_method):
            violations.append(f"{code}014 typed {op} surface contains Any: RPC client")
    return violations


def _scan_shared_adapter_surface(
    op: str, root: Path, overrides: Mapping[str, str]
) -> list[str]:
    paths = _paths(op)
    violations: list[str] = []
    public_source = _try_read_source(root, paths["public"], overrides)
    if public_source is not None:
        violations.extend(_scan_public_adapter(op, public_source, include_freecad_call=False))
    leaf_tree = _leaf_tree(root, op, overrides)
    if leaf_tree is not None:
        violations.extend(_scan_leaf_generated_execution(op, leaf_tree))
    violations.extend(_scan_protocol_vendors(op, root, overrides))
    violations.extend(_scan_typed_surface_any(op, root, overrides))
    return violations


def _one_level_module_callees(fn: ast.FunctionDef, tree: ast.Module) -> list[ast.FunctionDef]:
    helpers: list[ast.FunctionDef] = []
    seen: set[str] = set()
    for name in _called_names(fn):
        if name in seen:
            continue
        helper = _try_function(tree, name)
        if helper is None:
            continue
        seen.add(name)
        helpers.append(helper)
    return helpers


def _native_apply_surfaces(leaf_tree: ast.Module, op: str) -> list[ast.FunctionDef]:
    surfaces: list[ast.FunctionDef] = []
    seen: set[int] = set()

    def _add(fn: ast.FunctionDef | None) -> None:
        if fn is None:
            return
        key = id(fn)
        if key in seen:
            return
        seen.add(key)
        surfaces.append(fn)
        for helper in _one_level_module_callees(fn, leaf_tree):
            helper_key = id(helper)
            if helper_key in seen:
                continue
            seen.add(helper_key)
            surfaces.append(helper)

    _add(_try_function(leaf_tree, f"apply_{op}"))
    try:
        _add(_class_method(leaf_tree, f"_{pascal(op)}Execution", "apply"))
    except ValueError:
        pass
    return surfaces


def _external_effect_hits(nodes: list[ast.FunctionDef]) -> list[str]:
    hits: list[str] = []
    for node in nodes:
        text = ast.unparse(node)
        for marker in _EXTERNAL_APPLY_MARKERS:
            if marker in text:
                hits.append(marker)
        external_attrs = sorted(
            name
            for name in _called_names(node)
            if name.startswith("export_") or name in {"create_mesh", "invoke"}
        )
        if external_attrs:
            hits.append(", ".join(external_attrs))
    return hits


def _scan_document_query(op: str, root: Path, overrides: Mapping[str, str]) -> list[str]:
    violations: list[str] = []
    leaf_tree = _leaf_tree(root, op, overrides)
    if leaf_tree is not None:
        pipeline = _uses_mutation_pipeline(leaf_tree, op)
        if pipeline:
            violations.append(
                f"QUERY {op} uses fake mutation pipeline ({', '.join(sorted(set(pipeline)))})"
            )
        transactions = sorted(
            {"openTransaction", "commitTransaction", "abortTransaction"}
            & set(_called_names(leaf_tree))
        )
        if transactions:
            violations.append(f"QUERY {op} opens a document transaction ({', '.join(transactions)})")
    mutation_tree = _mutation_tree(root, op, overrides)
    if mutation_tree is not None:
        pipeline = _uses_mutation_pipeline(mutation_tree, op)
        if pipeline:
            violations.append(
                f"QUERY {op} uses fake mutation pipeline ({', '.join(sorted(set(pipeline)))})"
            )
    contract_source = _contract_source(root, op, overrides)
    if contract_source and _contract_uses_committed_outcome(contract_source):
        violations.append(
            f'QUERY {op} success contract uses outcome "committed" / committed=True for a measurement'
        )
    return _dedupe(violations + _scan_shared_adapter_surface(op, root, overrides))


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _scan_document_lifecycle(op: str, root: Path, overrides: Mapping[str, str]) -> list[str]:
    violations: list[str] = []
    paths = _paths(op)
    leaf_source = _try_read_source(root, paths["leaf"], overrides)
    if leaf_source is None:
        return _scan_shared_adapter_surface(op, root, overrides)
    leaf_tree = ast.parse(leaf_source, filename=paths["leaf"])
    pipeline = _uses_mutation_pipeline(leaf_tree, op)
    if pipeline:
        violations.append(f"LIFE {op} uses mutation pipeline as perform step")
    mutation_tree = _mutation_tree(root, op, overrides)
    if mutation_tree is not None and _uses_mutation_pipeline(mutation_tree, op):
        violations.append(f"LIFE {op} uses mutation pipeline as perform step")

    run_fn = _try_function(leaf_tree, f"run_{op}")
    execution_run = None
    try:
        execution_run = _class_method(leaf_tree, f"_{pascal(op)}Execution", "run")
    except ValueError:
        execution_run = None

    if run_fn is not None:
        lifecycle_in_run = _lifecycle_api_mentions(run_fn)
        if lifecycle_in_run:
            run_text = ast.unparse(run_fn)
            run_index = run_text.find(".run(")
            for api in lifecycle_in_run:
                api_index = run_text.find(f'"{api}"')
                if api_index == -1:
                    api_index = run_text.find(api)
                if run_index != -1 and api_index > run_index:
                    violations.append(
                        f"LIFE {op} lifecycle API ({api}) runs after native SUCCESS"
                    )
                else:
                    violations.append(
                        f"LIFE {op} lifecycle API ({api}) runs before native mutation "
                        "rather than in a dedicated perform step"
                    )

    apply_fn = _try_function(leaf_tree, f"apply_{op}")
    if apply_fn is not None and run_fn is not None:
        apply_writes = _WRITE_LIKE & set(_called_names(apply_fn))
        if not apply_writes and _lifecycle_api_mentions(run_fn):
            violations.append(
                f"LIFE {op} pretending native commit performed close/open/reload (identity apply + native mutation)"
            )

    contract_source = _contract_source(root, op, overrides)
    if contract_source and _contract_uses_committed_outcome(contract_source):
        allowed = ", ".join(sorted(_LIFECYCLE_OUTCOMES))
        violations.append(
            f'LIFE {op} success contract outcome is "committed" (not {allowed})'
        )

    return _dedupe(violations + _scan_shared_adapter_surface(op, root, overrides))


def _scan_history_operation(op: str, root: Path, overrides: Mapping[str, str]) -> list[str]:
    violations: list[str] = []
    for history_op in ("undo", "redo"):
        paths = _paths(history_op)
        leaf_source = _try_read_source(root, paths["leaf"], overrides)
        if leaf_source is None:
            continue
        leaf_tree = ast.parse(leaf_source, filename=paths["leaf"])
        pipeline = _uses_mutation_pipeline(leaf_tree, history_op)
        if pipeline and history_op == op:
            violations.append(
                f"HIST {history_op} routed through run_{history_op}_native_mutation / "
                "commitCompatibilityMutation"
            )
        elif pipeline and history_op != op:
            violations.append(
                f"HIST {history_op} routed through run_{history_op}_native_mutation / "
                "commitCompatibilityMutation"
            )

    undo_source = _try_read_source(root, _paths("undo")["leaf"], overrides)
    redo_source = _try_read_source(root, _paths("redo")["leaf"], overrides)
    if undo_source and redo_source:
        undo_apply, undo_run = _history_perform_locations(undo_source, "undo")
        redo_apply, redo_run = _history_perform_locations(redo_source, "redo")
        if (undo_apply, undo_run) != (redo_apply, redo_run):
            if op in {"undo", "redo"}:
                violations.append("HIST undo/redo model split (post-commit vs in-apply)")

    if op in {"undo", "redo"}:
        violations.extend(_scan_shared_adapter_surface(op, root, overrides))
    return _dedupe(violations)


def _scan_external_effect(op: str, root: Path, overrides: Mapping[str, str]) -> list[str]:
    violations: list[str] = []
    paths = _paths(op)
    leaf_source = _try_read_source(root, paths["leaf"], overrides)
    if leaf_source is not None:
        leaf_tree = ast.parse(leaf_source, filename=paths["leaf"])
        external_hits = _external_effect_hits(_native_apply_surfaces(leaf_tree, op))
        if external_hits:
            violations.append(
                f"EXT {op} performs external effect inside native apply ({external_hits[0]})"
            )
    contract_source = _contract_source(root, op, overrides)
    if contract_source and _contract_uses_committed_outcome(contract_source):
        violations.append(
            f"EXT {op} success uses committed/rejected as if native rollback undoes the external effect"
        )
    return _dedupe(violations + _scan_shared_adapter_surface(op, root, overrides))


def _scan_gui_global(op: str, root: Path, overrides: Mapping[str, str]) -> list[str]:
    violations: list[str] = []
    paths = _paths(op)
    leaf_source = _try_read_source(root, paths["leaf"], overrides)
    if leaf_source is None:
        return violations
    leaf_tree = ast.parse(leaf_source, filename=paths["leaf"])
    pipeline = _uses_mutation_pipeline(leaf_tree, op)
    if pipeline:
        violations.append(f"GUI {op} uses document transaction / commit_native_mutation")
    transactions = sorted(
        {"openTransaction", "commitTransaction", "abortTransaction", "commit_native_mutation"}
        & set(_called_names(leaf_tree))
    )
    if transactions:
        violations.append(f"GUI {op} uses document transaction / commit_native_mutation")
    contract_source = _contract_source(root, op, overrides)
    if contract_source and _contract_uses_committed_outcome(contract_source):
        violations.append(
            f"GUI {op} success uses committed=True for session/color/view application"
        )
    return _dedupe(violations + _scan_shared_adapter_surface(op, root, overrides))


class _PolicyScanner(Protocol):
    def __call__(
        self, op: str, root: Path, overrides: Mapping[str, str]
    ) -> list[str]: ...


def _scan_document_mutation(op: str, root: Path, overrides: Mapping[str, str]) -> list[str]:
    return scan_feature_architecture(root, op, source_overrides=overrides)


_POLICY_SCANNERS: dict[str, _PolicyScanner] = {
    _ExecutionPolicy.DOCUMENT_MUTATION.value: _scan_document_mutation,
    _ExecutionPolicy.DOCUMENT_QUERY.value: _scan_document_query,
    _ExecutionPolicy.DOCUMENT_LIFECYCLE.value: _scan_document_lifecycle,
    _ExecutionPolicy.HISTORY_OPERATION.value: _scan_history_operation,
    _ExecutionPolicy.EXTERNAL_EFFECT.value: _scan_external_effect,
    _ExecutionPolicy.GUI_GLOBAL.value: _scan_gui_global,
}


def scan_op_architecture(
    root: Path,
    op: str,
    *,
    source_overrides: Mapping[str, str] | None = None,
) -> list[str]:
    """Dispatch architecture scanning to the execution-policy-specific gate."""

    overrides = source_overrides or {}
    if op == "body_create":
        from ci.check_body_create_contract import scan_body_create_architecture

        return scan_body_create_architecture(root, source_overrides=overrides)
    policy = policy_for_op(root, op)
    scanner = _POLICY_SCANNERS[policy]
    return scanner(op, root, overrides)


__all__ = [
    "policy_for_op",
    "scan_op_architecture",
]
