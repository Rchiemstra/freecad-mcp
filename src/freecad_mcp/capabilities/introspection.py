"""Introspect hand-written tool modules while bootstrapping manifests."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path
from typing import Any


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _tool_module_path(module_name: str) -> Path:
    return _repository_root() / "src" / "freecad_mcp" / f"{module_name}.py"


def _operation_from_call(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Name) and func.id.endswith("_operation"):
        return func.id
    if isinstance(func, ast.Name) and func.id in {"_removed", "tool_fail", "_result"}:
        if func.id == "_result" and call.args:
            inner = call.args[0]
            if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute):
                if (
                    isinstance(inner.func.value, ast.Call)
                    and isinstance(inner.func.value.func, ast.Name)
                    and inner.func.value.func.id == "server_connection"
                ):
                    return f"connection:{inner.func.attr}"
        if func.id in {"_removed", "tool_fail"}:
            return "legacy_removed_tool"
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Call):
        if (
            isinstance(func.value.func, ast.Name)
            and func.value.func.id == "server_connection"
        ):
            return f"connection:{func.attr}"
    return None


def _find_tool_function(tree: ast.Module, tool_name: str) -> ast.FunctionDef | None:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == tool_name:
            return node
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for child in ast.walk(node):
            if isinstance(child, ast.FunctionDef) and child.name == tool_name:
                return child
    return None


def _operation_from_function(function: ast.FunctionDef) -> str | None:
    for child in ast.walk(function):
        if not isinstance(child, ast.Call):
            continue
        if operation := _operation_from_call(child):
            return operation
    return None


def _defining_package(module_name: str) -> str:
    """Package that owns a ``tools_*.py`` register module."""

    return "freecad_mcp"


def _resolve_relative_import(
    package: str,
    *,
    level: int,
    module: str | None,
    symbol: str,
) -> str:
    """Resolve ``from ... import symbol`` against ``package``."""

    if level <= 0:
        if module:
            return f"{module}.{symbol}"
        return symbol
    parts = package.split(".")
    ascend = level - 1
    if ascend > len(parts):
        base = ""
    else:
        base = ".".join(parts[: len(parts) - ascend])
    if module:
        return f"{base}.{module}.{symbol}" if base else f"{module}.{symbol}"
    return f"{base}.{symbol}" if base else symbol


def _resolve_import_path(
    tree: ast.Module,
    symbol: str,
    *,
    module_name: str,
) -> str:
    if symbol.startswith("connection:"):
        return f"freecad_mcp.capabilities.gateway_refs.{symbol}"
    package = _defining_package(module_name)
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        for alias in node.names:
            if alias.name != symbol:
                continue
            imported = alias.asname or alias.name
            if imported != symbol:
                continue
            level = node.level or 0
            module = node.module
            if level > 0:
                return _resolve_relative_import(
                    package,
                    level=level,
                    module=module,
                    symbol=symbol,
                )
            if module:
                return f"{module}.{symbol}"
            return f"freecad_mcp.operations.{symbol}"
    return f"freecad_mcp.operations.{symbol}"


def import_operation_symbol(operation_path: str) -> Any:
    """Import an operation symbol or validate a gateway_refs descriptor."""

    if operation_path.startswith("freecad_mcp.capabilities.gateway_refs.connection:"):
        method = operation_path.rsplit("connection:", maxsplit=1)[-1]
        from ..freecad_client import FreeCADConnection

        if not method or not hasattr(FreeCADConnection, method):
            raise ImportError(
                f"gateway connection method {method!r} is not bound on FreeCADConnection"
            )
        return getattr(FreeCADConnection, method)
    if ".capabilities.inline." in operation_path:
        raise ImportError(f"inline placeholder is not importable: {operation_path}")
    module_name, _, attr = operation_path.rpartition(".")
    module = importlib.import_module(module_name)
    return getattr(module, attr)


def operation_path_for_tool(module_name: str, tool_name: str) -> str:
    """Return the operation symbol used by a tool registration helper."""

    path = _tool_module_path(module_name)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    helper_name = f"_register_{tool_name}"
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == helper_name:
            operation = _operation_from_function(node)
            if operation == "legacy_removed_tool":
                return "freecad_mcp.capabilities.legacy_shims.legacy_removed_tool"
            if operation is not None:
                return _resolve_import_path(tree, operation, module_name=module_name)

    tool_fn = _find_tool_function(tree, tool_name)
    if tool_fn is not None:
        operation = _operation_from_function(tool_fn)
        if operation == "legacy_removed_tool":
            return "freecad_mcp.capabilities.legacy_shims.legacy_removed_tool"
        if operation is not None:
            return _resolve_import_path(tree, operation, module_name=module_name)

    return f"freecad_mcp.capabilities.inline.{module_name}.{tool_name}"


def infer_execution_mode(operation_path: str, tool_name: str) -> str:
    if operation_path.endswith("legacy_shims.legacy_removed_tool"):
        return "typed_gateway"
    if operation_path.endswith(".core_ops.execute_ops.execute_code_operation"):
        return "generated_script"
    if tool_name == "execute_code":
        return "generated_script"
    return "typed_gateway"


def infer_gui_thread(tool_name: str, docstring: str) -> bool:
    if tool_name == "run_fem_analysis":
        return True
    lowered = docstring.lower()
    return "gui thread" in lowered or "blocks all other rpc" in lowered


def infer_mutation_class(module_name: str, tool_name: str) -> str:
    if module_name.startswith("tools_lease"):
        return "lease"
    if tool_name in {"execute_code", "execute_code_async", "run_transaction"}:
        return "execution"
    if tool_name.startswith(
        (
            "get_",
            "list_",
            "check_",
            "diagnose_",
            "inspect_",
            "measure_",
            "compare_",
            "validate_geometry",
            "compute_",
            "audit_",
            "match_",
            "get_dependency_graph",
            "geometric_diff",
            "placement_audit",
            "face_normal",
            "edge_axis",
            "find_faces",
            "find_edges",
        )
    ):
        return "read"
    if tool_name in {"get_view", "save_view_sequence", "encode_view_video"}:
        return "read"
    return "mutation"


__all__ = [
    "import_operation_symbol",
    "infer_execution_mode",
    "infer_gui_thread",
    "infer_mutation_class",
    "operation_path_for_tool",
]
