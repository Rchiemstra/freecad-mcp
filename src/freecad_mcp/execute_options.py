"""Options and helpers for scoped execute_code sessions (M1/M11)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


RecomputeMode = Literal["none", "target", "all"]


@dataclass
class ExecuteOptions:
    document: str | None = None
    recompute: RecomputeMode = "none"
    recompute_documents: list[str] | None = None
    read_only: bool = False
    restore_active_document: bool = True
    activate_document: bool = False
    capture_view: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "document": self.document,
            "recompute": self.recompute,
            "recompute_documents": self.recompute_documents,
            "read_only": self.read_only,
            "restore_active_document": self.restore_active_document,
            "activate_document": self.activate_document,
            "capture_view": self.capture_view,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ExecuteOptions:
        if not data:
            return cls()
        docs = data.get("recompute_documents")
        return cls(
            document=data.get("document"),
            recompute=data.get("recompute", "none"),
            recompute_documents=list(docs) if docs else None,
            read_only=bool(data.get("read_only", False)),
            restore_active_document=bool(data.get("restore_active_document", True)),
            activate_document=bool(data.get("activate_document", False)),
            capture_view=bool(data.get("capture_view", False)),
        )


def merge_execute_options(
    base: ExecuteOptions | None,
    **overrides: Any,
) -> ExecuteOptions:
    opts = base or ExecuteOptions()
    data = opts.to_dict()
    data.update({k: v for k, v in overrides.items() if v is not None})
    return ExecuteOptions.from_dict(data)
