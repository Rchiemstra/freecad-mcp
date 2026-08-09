"""Save As destination hash and alias checks."""

from __future__ import annotations

import hmac

from ..save_types.destination_conflict_error import DestinationConflictError
from ..save_types.invalid_save_request_error import InvalidSaveRequestError

try:
    from document_lease.identity import canonicalize_path
    from document_lease.model import FileBaseline
except ImportError:
    from addon.FreeCADMCP.document_lease.identity import canonicalize_path
    from addon.FreeCADMCP.document_lease.model import FileBaseline

from .baseline import _SHA256_RE, _baseline_differences


def verify_destination_hashes(
    service,
    destination: str,
    actual: FileBaseline,
    *,
    expected_destination_baseline: FileBaseline | None,
    expected_destination_sha256: str | None,
) -> None:
    if expected_destination_baseline is not None:
        differences = _baseline_differences(expected_destination_baseline, actual)
        if differences:
            raise DestinationConflictError(
                "Save As destination changed since it was inspected",
                stage="destination_preflight",
                path=destination,
                details={"differences": differences},
            )
    if expected_destination_sha256 is None:
        return
    if not _SHA256_RE.fullmatch(expected_destination_sha256):
        raise InvalidSaveRequestError(
            "expected destination SHA-256 is invalid",
            stage="destination_preflight",
            path=destination,
        )
    if not hmac.compare_digest(actual.sha256.lower(), expected_destination_sha256.lower()):
        raise DestinationConflictError(
            "Save As destination hash changed",
            stage="destination_preflight",
            path=destination,
            details={
                "expected_sha256": expected_destination_sha256.lower(),
                "actual_sha256": actual.sha256.lower(),
            },
        )


def reject_destination_aliases(
    service,
    destination: str,
    actual: FileBaseline,
    *,
    source_baseline: FileBaseline | None,
    source_comparison_key: str | None,
) -> None:
    if (
        source_baseline is not None
        and source_baseline.file_identity is not None
        and actual.file_identity is not None
        and source_baseline.file_identity.comparison_tuple()
        == actual.file_identity.comparison_tuple()
    ):
        raise DestinationConflictError(
            "Save As destination aliases the source file",
            stage="destination_preflight",
            path=destination,
        )
    if source_comparison_key is None:
        return
    _, destination_comparison = canonicalize_path(destination, platform=service.platform)
    if destination_comparison == source_comparison_key:
        raise DestinationConflictError(
            "Save As destination is the current document path",
            stage="destination_preflight",
            path=destination,
        )
