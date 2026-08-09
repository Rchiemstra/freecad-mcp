"""Acquisition validation helpers for document lease service operations."""

from __future__ import annotations

import os
import uuid
from typing import Any

from ..errors.coordination_error import CoordinationError
from ..errors.dirty_adoption_error import DirtyAdoptionError
from ..errors.lease_service_error import LeaseServiceError
from ..identity import file_identity_for_path
from ..model import FileBaseline, LeaseRecord


def normalize_acquisition_snapshot_id(
    snapshot_id: str | None,
) -> str | None:
    if not snapshot_id:
        return None
    try:
        return str(uuid.UUID(str(snapshot_id)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise LeaseServiceError(
            "acquisition snapshot ID must be a UUID"
        ) from exc


def validate_acquisition_reservation(
    record: LeaseRecord,
    *,
    expected_dirty: bool,
) -> None:
    if record.dirty != expected_dirty:
        raise DirtyAdoptionError(
            "the acquisition reservation does not match the requested lifecycle"
        )
    if expected_dirty and record.last_mutation_revision < 1:
        raise DirtyAdoptionError(
            "dirty adoption has no recorded pre-existing mutation"
        )


def assert_acquisition_snapshot_authority(
    record: LeaseRecord,
    normalized_snapshot: str | None,
) -> None:
    if record.snapshot_id is not None and record.snapshot_id != normalized_snapshot:
        raise CoordinationError(
            "acquisition snapshot does not match checkpointed authority"
        )


def _saved_document_acquisition_failures(
    *,
    info: os.stat_result,
    baseline: FileBaseline,
    current_identity: Any,
    record: LeaseRecord,
) -> list[str]:
    failures: list[str] = []
    if int(info.st_size) != baseline.size:
        failures.append("size changed")
    if int(info.st_mtime_ns) != baseline.mtime_ns:
        failures.append("modification time changed")
    if baseline.file_identity != current_identity:
        failures.append("file identity changed")
    if record.document.file_identity != current_identity:
        failures.append("registered document identity changed")
    return failures


def validate_saved_document_acquisition(
    *,
    path: str,
    baseline: FileBaseline | None,
    baseline_validated: bool,
    normalized_snapshot: str | None,
    identity_platform: Any,
    record: LeaseRecord,
) -> None:
    if not os.path.isfile(path):
        raise LeaseServiceError(
            "saved document path is missing or is not a regular file"
        )
    if not isinstance(baseline, FileBaseline):
        raise LeaseServiceError(
            "saved document acquisition requires a file baseline"
        )
    if not baseline_validated:
        raise LeaseServiceError(
            "saved document acquisition baseline was not validated"
        )
    if normalized_snapshot is None:
        raise LeaseServiceError(
            "saved document acquisition requires a recovery snapshot"
        )
    sha256 = str(baseline.sha256)
    if len(sha256) != 64 or any(ch not in "0123456789abcdef" for ch in sha256):
        raise LeaseServiceError("saved document baseline has an invalid SHA-256")
    try:
        info = os.stat(path)
    except OSError as exc:
        raise LeaseServiceError(f"saved document is unavailable: {exc}") from exc
    current_identity = file_identity_for_path(path, platform=identity_platform)
    failures = _saved_document_acquisition_failures(
        info=info,
        baseline=baseline,
        current_identity=current_identity,
        record=record,
    )
    if failures:
        raise CoordinationError(
            "saved document changed during acquisition: " + "; ".join(failures)
        )


def validate_unsaved_document_acquisition(
    path: str | None,
    baseline: FileBaseline | None,
    baseline_validated: bool,
) -> None:
    if path:
        return
    if baseline is not None or baseline_validated:
        raise LeaseServiceError(
            "unsaved document acquisition cannot have a file baseline"
        )
