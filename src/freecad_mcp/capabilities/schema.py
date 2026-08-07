"""Capability manifest schema (Stage 7 / Phase 20)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ExecutionMode(StrEnum):
    """How a capability reaches FreeCAD."""

    TYPED_GATEWAY = "typed_gateway"
    GENERATED_SCRIPT = "generated_script"
    ESCAPE_HATCH = "escape_hatch"


class MutationClass(StrEnum):
    """Mutation classification carried into gateway dispatch."""

    READ = "read"
    MUTATION = "mutation"
    GUI_MUTATION = "gui_mutation"
    LEASE = "lease"
    EXECUTION = "execution"


@dataclass(frozen=True, slots=True)
class ToolEntry:
    """One MCP tool declared in a subject manifest."""

    name: str
    docstring: str
    signature: str
    operation_path: str
    rpc_method: str
    execution_mode: ExecutionMode
    gui_thread: bool
    mutation_class: MutationClass
    escape_hatch_impl: str | None = None
    register_module: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "docstring": self.docstring,
            "signature": self.signature,
            "operation_path": self.operation_path,
            "rpc_method": self.rpc_method,
            "execution_mode": self.execution_mode.value,
            "gui_thread": self.gui_thread,
            "mutation_class": self.mutation_class.value,
        }
        if self.escape_hatch_impl is not None:
            payload["escape_hatch_impl"] = self.escape_hatch_impl
        if self.register_module is not None:
            payload["register_module"] = self.register_module
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ToolEntry:
        return cls(
            name=str(data["name"]),
            docstring=str(data["docstring"]),
            signature=str(data["signature"]),
            operation_path=str(data["operation_path"]),
            rpc_method=str(data["rpc_method"]),
            execution_mode=ExecutionMode(str(data["execution_mode"])),
            gui_thread=bool(data["gui_thread"]),
            mutation_class=MutationClass(str(data["mutation_class"])),
            escape_hatch_impl=(
                None
                if data.get("escape_hatch_impl") is None
                else str(data["escape_hatch_impl"])
            ),
            register_module=(
                None
                if data.get("register_module") is None
                else str(data["register_module"])
            ),
        )


@dataclass(frozen=True, slots=True)
class SubjectManifest:
    """Manifest owned by one capability subject."""

    subject: str
    register_modules: tuple[str, ...]
    tools: tuple[ToolEntry, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "register_modules": list(self.register_modules),
            "tools": [tool.to_dict() for tool in self.tools],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SubjectManifest:
        return cls(
            subject=str(data["subject"]),
            register_modules=tuple(str(name) for name in data["register_modules"]),
            tools=tuple(ToolEntry.from_dict(item) for item in data["tools"]),
        )


__all__ = [
    "ExecutionMode",
    "MutationClass",
    "SubjectManifest",
    "ToolEntry",
]
