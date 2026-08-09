"""Rollback coverage classification for mutation transactions."""

from __future__ import annotations

from enum import StrEnum


class RollbackCoverage(StrEnum):
    COMPLETE = "complete"
    DOCUMENT_ONLY = "document_only"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
