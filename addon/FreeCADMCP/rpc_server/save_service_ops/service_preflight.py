"""SaveService extracted methods."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from typing import Any

from ..save_types.baseline_required_error import BaselineRequiredError
from ..save_types.destination_conflict_error import DestinationConflictError
from ..save_types.invalid_save_request_error import InvalidSaveRequestError
from ..save_types.save_preflight import SavePreflight

try:
    from document_lease.identity import DocumentIdentityError, canonicalize_path
    from document_lease.model import FileBaseline
except ImportError:
    from addon.FreeCADMCP.document_lease.identity import (
        DocumentIdentityError,
        canonicalize_path,
    )
    from addon.FreeCADMCP.document_lease.model import FileBaseline

from .baseline import compare_file_to_baseline
from .service_destination import reject_destination_aliases, verify_destination_hashes

DomainValidator = Callable[[str, str], Mapping[str, Any] | bool | None]
DestinationGuardFactory = Callable[[str], AbstractContextManager[Any]]


def canonical_path(service, path: str | os.PathLike[str]) -> tuple[str, str]:
    try:
        return canonicalize_path(path, platform=service.platform)
    except (OSError, DocumentIdentityError, TypeError, ValueError) as exc:
        raise InvalidSaveRequestError(
            f"invalid save path: {exc}", stage="request_validation"
        ) from exc

def preflight_source_path(
    service,
    source_path: str | os.PathLike[str] | None,
    *,
    expected_baseline: FileBaseline | None,
    expected_path: str | os.PathLike[str] | None = None,
    required: bool,
) -> tuple[str | None, str | None, FileBaseline | None]:
    if not source_path:
        if required:
            raise InvalidSaveRequestError(
                "same-path save requires a document with a saved path",
                stage="preflight",
            )
        if expected_baseline is not None:
            raise InvalidSaveRequestError(
                "an unsaved document cannot have a file baseline",
                stage="preflight",
            )
        return None, None, None
    canonical, comparison = canonical_path(service, source_path)
    if expected_path is not None:
        asserted, asserted_comparison = canonical_path(service, expected_path)
        if comparison != asserted_comparison:
            raise InvalidSaveRequestError(
                "live document path does not match the requested document identity",
                stage="preflight",
                path=canonical,
                details={"expected_path": asserted},
            )
    if expected_baseline is None:
        raise BaselineRequiredError(
            "a saved document requires its last accepted baseline",
            stage="preflight",
            path=canonical,
        )
    observed = compare_file_to_baseline(
        canonical,
        expected_baseline,
        platform=service.platform,
        baseline_reader=service._baseline_reader,
    )
    return canonical, comparison, observed

def prepare_save(
    service,
    source_path: str | os.PathLike[str] | None,
    *,
    expected_baseline: FileBaseline,
    expected_path: str | os.PathLike[str] | None = None,
    validation_profile: str = "default",
) -> SavePreflight:
    """Perform the full compare-before-save hash off the GUI thread."""

    canonical, comparison, observed = preflight_source_path(service, 
        source_path,
        expected_baseline=expected_baseline,
        expected_path=expected_path,
        required=True,
    )
    assert canonical is not None
    assert comparison is not None
    assert observed is not None
    return SavePreflight(
        mode="save",
        path=canonical,
        comparison_key=comparison,
        previous_path=canonical,
        previous_comparison_key=comparison,
        source_baseline=observed,
        validation_profile=validation_profile,
        destination_preexisted=True,
        destination_baseline=observed,
    )

def prepare_save_as(
    service,
    source_path: str | os.PathLike[str] | None,
    destination: str | os.PathLike[str],
    *,
    source_baseline: FileBaseline | None,
    overwrite: bool = False,
    expected_destination_sha256: str | None = None,
    expected_destination_baseline: FileBaseline | None = None,
    validation_profile: str = "default",
) -> SavePreflight:
    """Hash source/destination after the lease reserves the destination."""

    canonical_destination, destination_comparison = canonical_path(service, destination)
    parent = os.path.dirname(canonical_destination) or os.curdir
    if not os.path.isdir(parent):
        raise InvalidSaveRequestError(
            "Save As destination parent does not exist",
            stage="destination_preflight",
            path=canonical_destination,
        )
    source, source_comparison, observed_source = preflight_source_path(service, 
        source_path,
        expected_baseline=source_baseline,
        required=False,
    )
    destination_preexisted, observed_destination = (
        preflight_destination(service, 
            canonical_destination,
            source_baseline=source_baseline,
            source_comparison_key=source_comparison,
            overwrite=overwrite,
            expected_destination_sha256=expected_destination_sha256,
            expected_destination_baseline=expected_destination_baseline,
        )
    )
    return SavePreflight(
        mode="save_as",
        path=canonical_destination,
        comparison_key=destination_comparison,
        previous_path=source,
        previous_comparison_key=source_comparison,
        source_baseline=observed_source,
        validation_profile=validation_profile,
        destination_preexisted=destination_preexisted,
        destination_baseline=observed_destination,
    )


def preflight_destination(
    service,
    destination: str,
    *,
    source_baseline: FileBaseline | None,
    source_comparison_key: str | None,
    overwrite: bool,
    expected_destination_sha256: str | None,
    expected_destination_baseline: FileBaseline | None,
) -> tuple[bool, FileBaseline | None]:
    exists = os.path.lexists(destination)
    if not exists:
        if expected_destination_sha256 is not None or (
            expected_destination_baseline is not None
        ):
            raise DestinationConflictError(
                "expected Save As destination no longer exists",
                stage="destination_preflight",
                path=destination,
            )
        return False, None
    if not os.path.isfile(destination):
        raise DestinationConflictError(
            "Save As destination is not a regular file",
            stage="destination_preflight",
            path=destination,
        )
    if not overwrite:
        raise DestinationConflictError(
            "Save As destination already exists and overwrite is false",
            stage="destination_preflight",
            path=destination,
        )
    if expected_destination_baseline is None and expected_destination_sha256 is None:
        raise DestinationConflictError(
            "overwriting a destination requires its expected SHA-256",
            stage="destination_preflight",
            path=destination,
        )
    try:
        actual = service._baseline_reader(destination, platform=service.platform)
    except (OSError, DocumentIdentityError) as exc:
        raise DestinationConflictError(
            f"unable to verify Save As destination: {exc}",
            stage="destination_preflight",
            path=destination,
        ) from exc
    verify_destination_hashes(
        service,
        destination,
        actual,
        expected_destination_baseline=expected_destination_baseline,
        expected_destination_sha256=expected_destination_sha256,
    )
    reject_destination_aliases(
        service,
        destination,
        actual,
        source_baseline=source_baseline,
        source_comparison_key=source_comparison_key,
    )
    return True, actual
