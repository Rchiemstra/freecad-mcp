"""Finalize save-and-release result."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .save_result import SaveResult


@dataclass(frozen=True)
class FinalizeResult:
    save: SaveResult
    verified_state: Any = None
    release_result: Any = None
    released: bool = False

    def to_dict(self) -> dict[str, Any]:
        result = {
            "ok": True,
            "save": self.save.to_dict(),
            "released": self.released,
        }
        if isinstance(self.verified_state, Mapping):
            result["verified_state"] = dict(self.verified_state)
        if isinstance(self.release_result, Mapping):
            result["release"] = dict(self.release_result)
        return result

FinalizeResult.__module__ = "rpc_server.save_service"
