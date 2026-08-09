"""Scanners used by the executable architecture-refactor baseline."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from tests.helpers.architecture_authority import (
    authority_symbol_census as _authority_symbol_census,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "post_collaboration_compatibility_surface.json"
PRODUCTION_ROOTS = (ROOT / "addon" / "FreeCADMCP", ROOT / "src" / "freecad_mcp")
FROZEN_DEPRECATION_RESULT = {
    "success": False,
    "ok": False,
    "error_code": "LEGACY_LEASE_AUTHORITY_REMOVED",
    "error": "Document authority is owned by native FreeCAD collaboration.",
}


def load_manifest() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def production_python_files() -> list[Path]:
    return sorted(path for root in PRODUCTION_ROOTS for path in root.rglob("*.py"))


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def rpc_mod_census() -> dict[str, dict[str, int]]:
    census: dict[str, dict[str, int]] = {}
    for path in production_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        definitions = sum(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "_rpc_mod"
            for node in ast.walk(tree)
        )
        loaded_references = sum(
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id == "_rpc_mod"
            for node in ast.walk(tree)
        )
        runtime_calls = sum(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_rpc_mod"
            for node in ast.walk(tree)
        )
        import_bindings = sum(
            isinstance(node, ast.ImportFrom)
            and any(alias.name == "_rpc_mod" for alias in node.names)
            for node in ast.walk(tree)
        )
        exported_names = sum(
            isinstance(node, ast.Constant) and node.value == "_rpc_mod"
            for node in ast.walk(tree)
        )
        if definitions or loaded_references or import_bindings or exported_names:
            census[relative(path)] = {
                "definitions": definitions,
                "loaded_references": loaded_references,
                "runtime_calls": runtime_calls,
                "import_bindings": import_bindings,
                "exported_names": exported_names,
            }
    return census


def is_sys_modules(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "sys"
        and node.attr == "modules"
    )


def nearest_function(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> str:
    current = parents.get(node)
    while current is not None:
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current.name
        current = parents.get(current)
    return "<module>"


def lookup_target(node: ast.AST | None) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if node is None:
        return "<missing>"
    return ast.unparse(node)


def dynamic_lookup_classification(
    path: str, function: str, kind: str, target: str
) -> str:
    if (
        path
        in {
            "addon/FreeCADMCP/document_lock_ops/module_aliases.py",
            "addon/FreeCADMCP/lock_indicator_ops/module_aliases.py",
        }
        and function == "_publish_aliases"
        and kind == "sys_modules_get"
        and target in {"qualified", "name"}
    ):
        return "compatibility_alias"
    if "/settings_ops/" in path and kind == "sys_modules_subscript":
        return "runtime_dependency_locator"
    if path.endswith("/observer_ops/runtime_providers.py") and function == (
        "qt_or_direct_queue"
    ):
        return "module_probe"
    if target in {"FreeCAD", "FreeCADGui", "Preferences"} or "PySide" in target:
        return "module_probe"
    if "/tool_exports/" in path:
        return "registration_barrel"
    if path.endswith("/tool_registration.py"):
        return "generated_registration_locator"
    if path.startswith("src/freecad_mcp/capabilities/") and function in {
        "import_operation_symbol",
        "all_subject_manifests",
        "_import_symbol",
    }:
        return "generated_registration_locator"
    return "runtime_locator"


def dynamic_module_lookup_census() -> list[dict[str, Any]]:
    occurrences: list[dict[str, Any]] = []
    for path in production_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        parents = {
            child: parent
            for parent in ast.walk(tree)
            for child in ast.iter_child_nodes(parent)
        }
        for node in ast.walk(tree):
            kind = ""
            target = ""
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
                and is_sys_modules(node.func.value)
            ):
                kind = "sys_modules_get"
                target = lookup_target(node.args[0] if node.args else None)
            elif (
                isinstance(node, ast.Subscript)
                and isinstance(node.ctx, ast.Load)
                and is_sys_modules(node.value)
            ):
                kind = "sys_modules_subscript"
                target = lookup_target(node.slice)
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "importlib"
                and node.func.attr == "import_module"
            ):
                kind = "importlib_import_module"
                target = lookup_target(node.args[0] if node.args else None)
            elif (
                isinstance(node, ast.Compare)
                and len(node.ops) == 1
                and isinstance(node.ops[0], ast.In)
                and len(node.comparators) == 1
                and is_sys_modules(node.comparators[0])
            ):
                kind = "sys_modules_contains"
                target = lookup_target(node.left)
            if kind:
                path_text = relative(path)
                function = nearest_function(node, parents)
                classification = dynamic_lookup_classification(
                    path_text, function, kind, target
                )
                occurrences.append(
                    {
                        "path": path_text,
                        "line": node.lineno,
                        "column": node.col_offset,
                        "function": function,
                        "kind": kind,
                        "target": target,
                        "classification": classification,
                    }
                )
    return sorted(
        occurrences,
        key=lambda item: (
            item["path"], item["line"], item["column"], item["kind"]
        )
    )


def local_import_locator_census() -> list[dict[str, Any]]:
    targets = {"server", "rpc_server", "document_lock", "document_lease", "core_authority"}
    occurrences: list[dict[str, Any]] = []
    for path in production_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        parents = {
            child: parent
            for parent in ast.walk(tree)
            for child in ast.iter_child_nodes(parent)
        }
        for node in ast.walk(tree):
            imported: list[str] = []
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                prefix = "." * node.level + (node.module or "")
                separator = "" if not prefix or prefix.endswith(".") else "."
                joined_targets = [
                    f"{prefix}{separator}{alias.name}" for alias in node.names
                ]
                imported.extend(joined_targets)
                normalized_prefix = prefix.lstrip(".")
                prefix_parts = normalized_prefix.split(".")
                is_project_runtime_base = (
                    prefix.startswith(".")
                    or len(prefix_parts) == 1
                    or prefix_parts[0] in targets
                    or normalized_prefix.startswith(
                        ("addon.FreeCADMCP.", "FreeCADMCP.", "freecad_mcp.")
                    )
                )
                if (
                    is_project_runtime_base
                    and prefix.rsplit(".", maxsplit=1)[-1] in targets
                    and not any(
                        target.rsplit(".", maxsplit=1)[-1] in targets
                        for target in joined_targets
                    )
                ):
                    imported.append(prefix)
            for target in imported:
                if target.rsplit(".", maxsplit=1)[-1] not in targets:
                    continue
                path_text = relative(path)
                function = nearest_function(node, parents)
                is_bootstrap_root_binding = path_text == (
                    "addon/FreeCADMCP/InitGui.py"
                ) and (function, target) in {
                    ("Initialize", "rpc_server.rpc_server"),
                    ("_auto_start_mcp", "rpc_server.rpc_server"),
                    (
                        "_initialize_rpc_runtime_shutdown",
                        "rpc_server.rpc_server",
                    ),
                }
                is_static_compatibility_binding = function == "<module>" and (
                    path_text.endswith(
                        "/rpc_server/lease_runtime_ops/imports.py"
                    )
                    and target
                    in {
                        "addon.FreeCADMCP.document_lease",
                        "addon.FreeCADMCP.document_lock",
                        "document_lease",
                        "document_lock",
                    }
                )
                is_static_authority_binding = (
                    path_text
                    == "addon/FreeCADMCP/rpc_server/rpc_server.py"
                    and function == "<module>"
                    and target
                    in {
                        "..document_lease.core_authority",
                        "document_lease.core_authority",
                    }
                )
                occurrences.append(
                    {
                        "path": path_text,
                        "line": node.lineno,
                        "column": node.col_offset,
                        "function": function,
                        "target": target,
                        "classification": (
                            "bootstrap_root_binding"
                            if is_bootstrap_root_binding
                            else (
                                "static_authority_binding"
                                if is_static_authority_binding
                                else (
                                    "static_compatibility_binding"
                                    if is_static_compatibility_binding
                                    else (
                                        "temporary_authority_locator"
                                        if target.endswith("core_authority")
                                        else "runtime_singleton_locator"
                                    )
                                )
                            )
                        ),
                    }
                )
    return sorted(
        occurrences,
        key=lambda item: (item["path"], item["line"], item["column"], item["target"]),
    )


def authority_symbol_census() -> dict[str, list[dict[str, Any]]]:
    return _authority_symbol_census(
        root=ROOT,
        production_files=production_python_files(),
    )


def _mutable_lease_call_target(node: ast.Call) -> str:
    direct_targets = {
        "create_sidecar",
        "delete_sidecar",
        "replace_sidecar",
        "validate_transition",
    }
    if isinstance(node.func, ast.Name):
        return node.func.id if node.func.id in direct_targets else ""
    if not isinstance(node.func, ast.Attribute):
        return ""
    if node.func.attr in {"revised", "transitioned"}:
        return f"LeaseRecord.{node.func.attr}"
    if node.func.attr == "validate_transition":
        return "validate_transition"
    if node.func.attr in {"create", "delete"}:
        return f"SidecarStore.{node.func.attr}"
    if node.func.attr == "replace" and any(
        keyword.arg == "expected" for keyword in node.keywords
    ):
        return "SidecarStore.replace"
    return ""


def mutable_lease_caller_census() -> list[dict[str, Any]]:
    """Enumerate the live lease/sidecar mutation calls Phase 18 must remove."""

    lease_root = ROOT / "addon" / "FreeCADMCP" / "document_lease"
    occurrences: list[dict[str, Any]] = []
    for path in sorted(lease_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        parents = {
            child: parent
            for parent in ast.walk(tree)
            for child in ast.iter_child_nodes(parent)
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            target = _mutable_lease_call_target(node)
            if not target:
                continue
            occurrences.append(
                {
                    "path": relative(path),
                    "line": node.lineno,
                    "column": node.col_offset,
                    "function": nearest_function(node, parents),
                    "target": target,
                    "classification": "temporary_mutable_lease_caller",
                }
            )
    return sorted(
        occurrences,
        key=lambda item: (
            item["path"],
            item["line"],
            item["column"],
            item["target"],
        ),
    )
