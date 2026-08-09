from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .save_as_migration_role import SaveAsMigrationRole


@dataclass(frozen=True)
class SaveAsMigration:
    """Crash-recovery linkage shared by both Save As sidecars.

    An unsaved first-save has no adjacent source sidecar, so its source path
    pair is null.  A saved-document Save As always persists the source role on
    the source record and the destination role on the destination record.
    """

    migration_id: str
    source_canonical_path: str | None
    source_comparison_key: str | None
    destination_canonical_path: str
    destination_comparison_key: str
    role: SaveAsMigrationRole

    def to_dict(self) -> dict[str, Any]:
        return {
            "migration_id": self.migration_id,
            "source": {
                "canonical_path": self.source_canonical_path,
                "comparison_key": self.source_comparison_key,
            },
            "destination": {
                "canonical_path": self.destination_canonical_path,
                "comparison_key": self.destination_comparison_key,
            },
            "role": self.role.value,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> SaveAsMigration | None:
        if data is None:
            return None
        source = data["source"]
        destination = data["destination"]
        return cls(
            migration_id=str(data["migration_id"]),
            source_canonical_path=source["canonical_path"],
            source_comparison_key=source["comparison_key"],
            destination_canonical_path=str(destination["canonical_path"]),
            destination_comparison_key=str(destination["comparison_key"]),
            role=SaveAsMigrationRole(data["role"]),
        )

SaveAsMigration.__module__ = "document_lease.model"
