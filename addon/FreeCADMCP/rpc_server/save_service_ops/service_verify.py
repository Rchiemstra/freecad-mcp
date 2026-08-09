"""SaveService extracted methods."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from typing import Any

from ..save_types.archive_verification import ArchiveVerification
from ..save_types.domain_validation_error import DomainValidationError
from ..save_types.fcstd_verification_error import FcstdVerificationError
from ..save_types.invalid_save_request_error import InvalidSaveRequestError
from ..save_types.save_invocation import SaveInvocation
from ..save_types.save_result import SaveResult
from ..save_types.save_service_error import SaveServiceError
from ..save_types.saved_file_unstable_error import SavedFileUnstableError

try:
    from document_lease.identity import (
                file_identity_for_path,
    )
except ImportError:
    from addon.FreeCADMCP.document_lease.identity import (
        file_identity_for_path,
    )

from .baseline import (
    _baseline_differences,
    _call_baseline_reader,
    _identity_dict,
)
from .service_preflight import canonical_path
from .service_revalidate import capture_save_invocation_gui

DomainValidator = Callable[[str, str], Mapping[str, Any] | bool | None]
DestinationGuardFactory = Callable[[str], AbstractContextManager[Any]]


def verify_saved_file(
    service,
    invocation: SaveInvocation,
    *,
    domain_validator: DomainValidator | None = None,
) -> SaveResult:
    """Hash, inspect, and reopen a saved FCStd outside the GUI thread."""

    if not isinstance(invocation, SaveInvocation):
        raise InvalidSaveRequestError(
            "SaveInvocation is required for saved-file verification",
            stage="post_save_verification",
        )
    live_canonical = invocation.path
    baseline = _call_baseline_reader(
        service._baseline_reader,
        live_canonical,
        platform=service.platform,
        mutation_may_have_occurred=True,
    )
    try:
        archive = service._archive_verifier(live_canonical)
    except SaveServiceError:
        raise
    except Exception as exc:
        raise FcstdVerificationError(
            f"FCStd archive verification failed: {exc}",
            stage="archive_verification",
            path=live_canonical,
            mutation_may_have_occurred=True,
        ) from exc
    if not isinstance(archive, ArchiveVerification):
        raise FcstdVerificationError(
            "archive verifier returned invalid data",
            stage="archive_verification",
            path=live_canonical,
            mutation_may_have_occurred=True,
        )
    validator = domain_validator or service._domain_validator
    domain_result: Mapping[str, Any] = {}
    if validator is not None:
        try:
            result = validator(
                live_canonical, invocation.validation_profile
            )
        except Exception as exc:
            raise DomainValidationError(
                f"saved document validation failed: {exc}",
                stage="domain_validation",
                path=live_canonical,
                mutation_may_have_occurred=True,
            ) from exc
        if result is False or (
            isinstance(result, Mapping)
            and result.get("ok", result.get("success", True)) is False
        ):
            details = dict(result) if isinstance(result, Mapping) else {}
            raise DomainValidationError(
                "saved document did not pass domain validation",
                stage="domain_validation",
                path=live_canonical,
                mutation_may_have_occurred=True,
                details=details,
            )
        if isinstance(result, Mapping):
            domain_result = dict(result)
    # Bind the recorded digest to the exact file that passed archive and
    # domain verification.  Each capture is internally stat-before/after;
    # comparing the two also detects replacement during worker validation.
    final_baseline = _call_baseline_reader(
        service._baseline_reader,
        live_canonical,
        platform=service.platform,
        mutation_may_have_occurred=True,
    )
    verification_race = _baseline_differences(baseline, final_baseline)
    if verification_race:
        raise SavedFileUnstableError(
            "saved file changed during archive or domain verification",
            stage="post_validation_hash",
            path=live_canonical,
            mutation_may_have_occurred=True,
            details={"differences": verification_race},
        )
    return SaveResult(
        mode=invocation.mode,
        path=live_canonical,
        previous_path=invocation.previous_path,
        baseline=final_baseline,
        archive=archive,
        validation_profile=invocation.validation_profile,
        domain_validation=domain_result,
        destination_preexisted=invocation.destination_preexisted,
    )

def revalidate_saved_document_gui(
    service, document: Any, result: SaveResult
) -> None:
    """Perform the final lightweight GUI-thread identity/dirty check.

    Full hashing and archive/domain validation have already completed on
    the RPC caller thread.  This check compares path, filesystem identity,
    size, and mtime so a change during the handoff blocks promotion without
    reintroducing expensive GUI-thread I/O.
    """

    canonical, comparison = canonical_path(service, result.path)
    capture_save_invocation_gui(service, 
        document,
        path=canonical,
        expected_comparison_key=comparison,
        mode=result.mode,
        previous_path=result.previous_path,
        validation_profile=result.validation_profile,
        destination_preexisted=result.destination_preexisted,
    )
    try:
        info = os.stat(canonical)
    except OSError as exc:
        raise SavedFileUnstableError(
            f"saved file disappeared before lease promotion: {exc}",
            stage="final_gui_revalidation",
            path=canonical,
            mutation_may_have_occurred=True,
        ) from exc
    differences: dict[str, dict[str, Any]] = {}
    if int(info.st_size) != result.baseline.size:
        differences["size"] = {
            "expected": result.baseline.size,
            "actual": int(info.st_size),
        }
    if int(info.st_mtime_ns) != result.baseline.mtime_ns:
        differences["mtime_ns"] = {
            "expected": result.baseline.mtime_ns,
            "actual": int(info.st_mtime_ns),
        }
    actual_identity = file_identity_for_path(
        canonical, platform=service.platform
    )
    if result.baseline.file_identity is not None and (
        actual_identity is None
        or actual_identity.comparison_tuple()
        != result.baseline.file_identity.comparison_tuple()
    ):
        differences["file_identity"] = {
            "expected": _identity_dict(result.baseline.file_identity),
            "actual": _identity_dict(actual_identity),
        }
    if differences:
        raise SavedFileUnstableError(
            "saved file changed after verification and before lease promotion",
            stage="final_gui_revalidation",
            path=canonical,
            mutation_may_have_occurred=True,
            details={"differences": differences},
        )

def _verify_saved_document(
    service,
    document: Any,
    *,
    path: str,
    expected_comparison_key: str,
    mode: str,
    previous_path: str | None,
    validation_profile: str,
    destination_preexisted: bool,
    domain_validator: DomainValidator | None,
) -> SaveResult:
    invocation = capture_save_invocation_gui(service, 
        document,
        path=path,
        expected_comparison_key=expected_comparison_key,
        mode=mode,
        previous_path=previous_path,
        validation_profile=validation_profile,
        destination_preexisted=destination_preexisted,
    )
    result = service.verify_saved_file(
        invocation, domain_validator=domain_validator
    )
    service.revalidate_saved_document_gui(document, result)
    return result
