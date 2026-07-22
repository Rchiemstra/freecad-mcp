"""Options and helpers for scoped execute_code sessions (M1/M11)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


RecomputeMode = Literal["none", "target", "all"]
ExecutionMode = Literal["gui", "worker", "auto"]
LinkPolicy = Literal["strict", "warn"]


@dataclass
class ExecuteOptions:
    document: str | None = None
    # Complete write scope for mutating code.  ``document`` remains the
    # primary/active document for compatibility; all other touched documents
    # must be declared here and independently leased.
    affected_documents: list[str] | None = None
    recompute: RecomputeMode = "none"
    recompute_documents: list[str] | None = None
    read_only: bool = False
    restore_active_document: bool = True
    activate_document: bool = False
    capture_view: bool = False
    execution_mode: ExecutionMode = "auto"
    timeout_seconds: float | None = None
    link_policy: LinkPolicy = "strict"
    # Set only by repository operation wrappers.  The public arbitrary-code
    # MCP tool deliberately does not expose this capability marker.
    generated_operation: bool = False
    operation_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "document": self.document,
            "affected_documents": self.affected_documents,
            "recompute": self.recompute,
            "recompute_documents": self.recompute_documents,
            "read_only": self.read_only,
            "restore_active_document": self.restore_active_document,
            "activate_document": self.activate_document,
            "capture_view": self.capture_view,
            "execution_mode": self.execution_mode,
            "timeout_seconds": self.timeout_seconds,
            "link_policy": self.link_policy,
            "generated_operation": self.generated_operation,
            "operation_id": self.operation_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ExecuteOptions:
        if not data:
            return cls()
        docs = data.get("recompute_documents")
        affected = data.get("affected_documents")
        return cls(
            document=data.get("document"),
            affected_documents=list(affected) if affected else None,
            recompute=data.get("recompute", "none"),
            recompute_documents=list(docs) if docs else None,
            read_only=bool(data.get("read_only", False)),
            restore_active_document=bool(data.get("restore_active_document", True)),
            activate_document=bool(data.get("activate_document", False)),
            capture_view=bool(data.get("capture_view", False)),
            execution_mode=data.get("execution_mode", "auto"),
            timeout_seconds=data.get("timeout_seconds"),
            link_policy=data.get("link_policy", "strict"),
            generated_operation=bool(data.get("generated_operation", False)),
            operation_id=data.get("operation_id"),
        )


def merge_execute_options(
    base: ExecuteOptions | None,
    **overrides: Any,
) -> ExecuteOptions:
    opts = base or ExecuteOptions()
    data = opts.to_dict()
    data.update({k: v for k, v in overrides.items() if v is not None})
    return ExecuteOptions.from_dict(data)
