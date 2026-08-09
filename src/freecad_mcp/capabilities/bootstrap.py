"""Bootstrap subject manifests from the frozen registry snapshot."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .introspection import (
    infer_execution_mode,
    infer_gui_thread,
    infer_mutation_class,
    operation_path_for_tool,
)
from .schema import ExecutionMode, MutationClass, SubjectManifest, ToolEntry
from .subjects import subject_for_register_module


def frozen_registry_snapshot_path() -> Path:
    return (
        Path(__file__).resolve().parents[3]
        / "tests"
        / "fixtures"
        / "mcp_tool_registry_contract_snapshot.json"
    )


def load_frozen_registry_snapshot() -> dict[str, Any]:
    return json.loads(frozen_registry_snapshot_path().read_text(encoding="utf-8"))


def _tools_by_register_module() -> dict[str, list[str]]:
    from freecad_mcp.tools_register_order import REGISTER_TOOL_MODULE_OBJECTS

    mapping: dict[str, list[str]] = {}
    for module in REGISTER_TOOL_MODULE_OBJECTS:
        module_name = module.__name__.rsplit(".", maxsplit=1)[-1]
        mapping[module_name] = []
    return mapping


def map_tools_to_register_modules(snapshot: dict[str, Any]) -> dict[str, list[str]]:
    from unittest.mock import MagicMock

    from freecad_mcp.collaboration_client import CollaborationClient
    from freecad_mcp.instrumented_server import InstrumentedFastMCP
    from freecad_mcp.server_ops.tool_dependencies import ToolDependencies
    from freecad_mcp.tools_register_order import REGISTER_TOOL_MODULE_OBJECTS

    tool_names = set(snapshot["tool_order"])
    mapping = _tools_by_register_module()
    mcp = InstrumentedFastMCP("manifest-bootstrap")
    connection = MagicMock(name="FreeCADConnection")
    dependencies = ToolDependencies(
        state=object(),
        get_freecad_connection=lambda: connection,
        recovery_compatibility=None,
        collaboration=CollaborationClient(connection),
        document_selector_input=dict,
    )

    for module in REGISTER_TOOL_MODULE_OBJECTS:
        module_name = module.__name__.rsplit(".", maxsplit=1)[-1]
        exports = module.register(mcp, dependencies=dependencies)
        mapping[module_name] = sorted(
            name for name in exports if name in tool_names
        )

    registered = {name for names in mapping.values() for name in names}
    if registered != tool_names:
        missing = sorted(tool_names - registered)
        extra = sorted(registered - tool_names)
        raise RuntimeError(
            "register module mapping mismatch: "
            f"missing={missing!r} extra={extra!r}"
        )
    return mapping


def build_tool_entry(
    *,
    module_name: str,
    tool_name: str,
    snapshot_tools: dict[str, dict[str, str]],
) -> ToolEntry:
    frozen = snapshot_tools[tool_name]
    operation_path = operation_path_for_tool(module_name, tool_name)
    execution_mode = ExecutionMode(infer_execution_mode(operation_path, tool_name))
    docstring = frozen["docstring"]
    return ToolEntry(
        name=tool_name,
        docstring=docstring,
        signature=frozen["signature"],
        operation_path=operation_path,
        rpc_method=tool_name,
        execution_mode=execution_mode,
        gui_thread=infer_gui_thread(tool_name, docstring),
        mutation_class=MutationClass(infer_mutation_class(module_name, tool_name)),
        register_module=module_name,
    )


def bootstrap_subject_manifests() -> tuple[SubjectManifest, ...]:
    snapshot = load_frozen_registry_snapshot()
    module_tools = map_tools_to_register_modules(snapshot)
    grouped: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))

    for module_name, tool_names in module_tools.items():
        subject = subject_for_register_module(module_name)
        grouped[subject][module_name] = tool_names

    manifests: list[SubjectManifest] = []
    for subject in sorted(grouped):
        register_modules = tuple(sorted(grouped[subject]))
        tool_entries: list[ToolEntry] = []
        for module_name in register_modules:
            for tool_name in grouped[subject][module_name]:
                tool_entries.append(
                    build_tool_entry(
                        module_name=module_name,
                        tool_name=tool_name,
                        snapshot_tools=snapshot["tools"],
                    )
                )
        manifests.append(
            SubjectManifest(
                subject=subject,
                register_modules=register_modules,
                tools=tuple(tool_entries),
            )
        )
    return tuple(manifests)


def render_subject_manifest_module(manifest: SubjectManifest) -> str:
    lines = [
        f'"""Capability manifest for {manifest.subject} (bootstrapped)."""',
        "",
        "from __future__ import annotations",
        "",
        "from ..schema import ExecutionMode, MutationClass, SubjectManifest, ToolEntry",
        "",
        "MANIFEST = SubjectManifest(",
        f'    subject="{manifest.subject}",',
        f"    register_modules={manifest.register_modules!r},",
        "    tools=(",
    ]
    for tool in manifest.tools:
        lines.append("        ToolEntry(")
        lines.append(f'            name="{tool.name}",')
        lines.append(f"            docstring={tool.docstring!r},")
        lines.append(f"            signature={tool.signature!r},")
        lines.append(f'            operation_path="{tool.operation_path}",')
        lines.append(f'            rpc_method="{tool.rpc_method}",')
        lines.append(
            f"            execution_mode=ExecutionMode.{tool.execution_mode.name},"
        )
        lines.append(f"            gui_thread={tool.gui_thread!r},")
        lines.append(
            f"            mutation_class=MutationClass.{tool.mutation_class.name},"
        )
        if tool.escape_hatch_impl is not None:
            lines.append(
                f"            escape_hatch_impl={tool.escape_hatch_impl!r},"
            )
        lines.append(f'            register_module="{tool.register_module}",')
        lines.append("        ),")
    lines.extend(
        [
            "    ),",
            ")",
            "",
        ]
    )
    return "\n".join(lines)


def write_subject_manifest_modules(
    manifests: tuple[SubjectManifest, ...] | None = None,
    *,
    root: Path | None = None,
) -> list[Path]:
    root = root or Path(__file__).resolve().parent
    manifests = manifests or bootstrap_subject_manifests()
    written: list[Path] = []
    for manifest in manifests:
        subject_dir = root / manifest.subject
        subject_dir.mkdir(parents=True, exist_ok=True)
        init_path = subject_dir / "__init__.py"
        if not init_path.exists():
            init_path.write_text(
                f'"""Capability subject package: {manifest.subject}."""\n',
                encoding="utf-8",
            )
        manifest_path = subject_dir / "manifest.py"
        manifest_path.write_text(
            render_subject_manifest_module(manifest),
            encoding="utf-8",
        )
        written.append(manifest_path)
    return written


__all__ = [
    "bootstrap_subject_manifests",
    "frozen_registry_snapshot_path",
    "load_frozen_registry_snapshot",
    "map_tools_to_register_modules",
    "render_subject_manifest_module",
    "write_subject_manifest_modules",
]
