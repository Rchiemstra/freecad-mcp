from __future__ import annotations

from enum import StrEnum


class SaveAsMigrationRole(StrEnum):
    __module__ = "document_lease.model"
    """The side of an in-flight Save As represented by one sidecar."""

    SOURCE = "source"
    DESTINATION = "destination"
