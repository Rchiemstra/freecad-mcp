"""Register MCP tools from capability manifests (shadow path)."""

from __future__ import annotations

import importlib
from typing import Any

from ..server_ops.tool_dependencies import ToolDependencies
from ..tools_register_order import REGISTER_TOOL_MODULE_OBJECTS
from .schema import ExecutionMode, SubjectManifest, ToolEntry


def _import_symbol(path: str) -> Any:
    module_name, _, attr = path.rpartition(".")
    module = importlib.import_module(module_name)
    return getattr(module, attr)


def register_tool_from_manifest(
    mcp: Any,
    entry: ToolEntry,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    del mcp
    if entry.execution_mode is ExecutionMode.ESCAPE_HATCH:
        if entry.escape_hatch_impl is None:
            raise ValueError(f"escape hatch entry {entry.name!r} missing impl path")
        exports[entry.name] = _import_symbol(entry.escape_hatch_impl)
        return
    del entry, dependencies, exports


def register_subject_manifest(
    mcp: Any,
    manifest: SubjectManifest,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    for entry in manifest.tools:
        if entry.execution_mode is ExecutionMode.ESCAPE_HATCH:
            register_tool_from_manifest(
                mcp,
                entry,
                dependencies=dependencies,
                exports=exports,
            )


def register_all_manifests(
    mcp: Any,
    manifests: tuple[SubjectManifest, ...],
    *,
    dependencies: ToolDependencies,
) -> dict[str, object]:
    manifest_tool_names = {entry.name for manifest in manifests for entry in manifest.tools}
    module_names = {
        module_name
        for manifest in manifests
        for module_name in manifest.register_modules
    }
    exports: dict[str, object] = {}
    for manifest in manifests:
        register_subject_manifest(
            mcp,
            manifest,
            dependencies=dependencies,
            exports=exports,
        )
    for module in REGISTER_TOOL_MODULE_OBJECTS:
        module_name = module.__name__.rsplit(".", maxsplit=1)[-1]
        if module_name not in module_names:
            continue
        module_exports = module.register(mcp, dependencies=dependencies)
        for name, tool in module_exports.items():
            if name.startswith("_") or name not in manifest_tool_names:
                continue
            exports[name] = tool
    return exports


def clear_template_cache_for_tests() -> None:
    return None


__all__ = [
    "clear_template_cache_for_tests",
    "register_all_manifests",
    "register_subject_manifest",
    "register_tool_from_manifest",
]
