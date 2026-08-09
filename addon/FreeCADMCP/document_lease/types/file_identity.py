from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FileIdentity:
    platform: str
    device: int | None = None
    inode: int | None = None
    volume_serial: int | None = None
    file_index: int | None = None

    def comparison_tuple(self) -> tuple[Any, ...]:
        if self.platform == "windows":
            return (self.platform, self.volume_serial, self.file_index)
        return (self.platform, self.device, self.inode)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"platform": self.platform}
        if self.platform == "windows":
            result.update(
                {"volume_serial": self.volume_serial, "file_index": self.file_index}
            )
        else:
            result.update({"device": self.device, "inode": self.inode})
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> FileIdentity | None:
        if data is None:
            return None
        return cls(
            platform=str(data["platform"]),
            device=data.get("device"),
            inode=data.get("inode"),
            volume_serial=data.get("volume_serial"),
            file_index=data.get("file_index"),
        )

FileIdentity.__module__ = "document_lease.model"
