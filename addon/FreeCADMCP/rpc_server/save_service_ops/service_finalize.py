"""SaveService extracted methods."""

from __future__ import annotations

import contextlib
import os
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from typing import Any

from ..save_types.baseline_required_error import BaselineRequiredError
from ..save_types.destination_conflict_error import DestinationConflictError
from ..save_types.finalize_result import FinalizeResult
from ..save_types.invalid_save_request_error import InvalidSaveRequestError
from ..save_types.lifecycle_callback_error import LifecycleCallbackError
from ..save_types.save_result import SaveResult
from ..save_types.save_service_error import SaveServiceError

try:
    from document_lease.model import FileBaseline
except ImportError:
    from addon.FreeCADMCP.document_lease.model import FileBaseline

from .document_state import (
    _document_filename,
)
from .service_preflight import canonical_path

DomainValidator = Callable[[str, str], Mapping[str, Any] | bool | None]
DestinationGuardFactory = Callable[[str], AbstractContextManager[Any]]


def save_document_as(
    service,
    document: Any,
    destination: str | os.PathLike[str],
    *,
    source_baseline: FileBaseline | None,
    overwrite: bool = False,
    expected_destination_sha256: str | None = None,
    expected_destination_baseline: FileBaseline | None = None,
    validation_profile: str = "default",
    destination_guard: DestinationGuardFactory | None = None,
    destination_commit: Callable[[SaveResult], Any] | None = None,
    domain_validator: DomainValidator | None = None,
) -> SaveResult:
    """Preflight and verify Save As while an optional destination guard is held.

    In enforce mode ``destination_guard`` should reserve/publish the
    destination sidecar before this method enters its critical section.
    ``destination_commit`` runs after verification but before that guard is
    released, allowing the lease service to promote the destination record
    and migrate document aliases conservatively.
    """

    canonical_destination, _destination_comparison = canonical_path(service, destination)
    parent = os.path.dirname(canonical_destination) or os.curdir
    if not os.path.isdir(parent):
        raise InvalidSaveRequestError(
            "Save As destination parent does not exist",
            stage="destination_preflight",
            path=canonical_destination,
        )
    source_path = _document_filename(document)
    guard_factory = destination_guard or (lambda _path: contextlib.nullcontext())
    save_started = False
    try:
        reservation = guard_factory(canonical_destination)
        with reservation:
            preflight = service.prepare_save_as(
                source_path,
                canonical_destination,
                source_baseline=source_baseline,
                overwrite=overwrite,
                expected_destination_sha256=expected_destination_sha256,
                expected_destination_baseline=expected_destination_baseline,
                validation_profile=validation_profile,
            )
            save_started = True
            invocation = service.invoke_save_as_gui(document, preflight)
            result = service.verify_saved_file(
                invocation,
                domain_validator=domain_validator,
            )
            service.revalidate_saved_document_gui(document, result)
            if destination_commit is not None:
                try:
                    destination_commit(result)
                except Exception as exc:
                    raise LifecycleCallbackError(
                        f"destination lease promotion failed: {exc}",
                        stage="destination_commit",
                        path=result.path,
                        mutation_may_have_occurred=True,
                        details={"save_result": result.to_dict()},
                    ) from exc
            return result
    except SaveServiceError:
        raise
    except Exception as exc:
        raise DestinationConflictError(
            f"unable to reserve or release Save As destination: {exc}",
            stage="destination_guard",
            path=canonical_destination,
            mutation_may_have_occurred=save_started,
        ) from exc

def finalize_document_edit(
    service,
    document: Any,
    *,
    save_mode: str,
    expected_baseline: FileBaseline | None,
    destination: str | os.PathLike[str] | None = None,
    overwrite: bool = False,
    expected_destination_sha256: str | None = None,
    expected_destination_baseline: FileBaseline | None = None,
    validation_profile: str = "default",
    destination_guard: DestinationGuardFactory | None = None,
    destination_commit: Callable[[SaveResult], Any] | None = None,
    domain_validator: DomainValidator | None = None,
    mark_verified: Callable[[SaveResult], Any] | None = None,
    guarded_release: Callable[[SaveResult], Any] | None = None,
) -> FinalizeResult:
    """Verify a save, publish its baseline, then invoke guarded release.

    ``mark_verified`` should call ``DocumentLeaseService.mark_save_verified``
    with ``result.baseline``.  ``guarded_release`` should then call the
    service's clean CAS release.  Neither callback runs unless filesystem,
    FCStd, dirty-state, and domain verification all succeeded.
    """

    normalized_mode = str(save_mode).strip().lower().replace("-", "_")
    if normalized_mode == "save":
        if expected_baseline is None:
            raise BaselineRequiredError(
                "same-path finalization requires a baseline",
                stage="request_validation",
            )
        result = service.save_document(
            document,
            expected_baseline=expected_baseline,
            validation_profile=validation_profile,
            domain_validator=domain_validator,
        )
    elif normalized_mode in {"save_as", "saveas", "first_save"}:
        if destination is None:
            raise InvalidSaveRequestError(
                "Save As finalization requires a destination",
                stage="request_validation",
            )
        result = service.save_document_as(
            document,
            destination,
            source_baseline=expected_baseline,
            overwrite=overwrite,
            expected_destination_sha256=expected_destination_sha256,
            expected_destination_baseline=expected_destination_baseline,
            validation_profile=validation_profile,
            destination_guard=destination_guard,
            destination_commit=destination_commit,
            domain_validator=domain_validator,
        )
    else:
        raise InvalidSaveRequestError(
            f"unsupported finalization save mode: {save_mode!r}",
            stage="request_validation",
        )

    verified_state = None
    if mark_verified is not None:
        try:
            verified_state = mark_verified(result)
        except Exception as exc:
            raise LifecycleCallbackError(
                f"verified baseline could not be committed: {exc}",
                stage="mark_save_verified",
                path=result.path,
                mutation_may_have_occurred=True,
                details={"save_result": result.to_dict()},
            ) from exc
    release_result = None
    if guarded_release is not None:
        try:
            release_result = guarded_release(result)
        except Exception as exc:
            raise LifecycleCallbackError(
                f"verified document could not be released: {exc}",
                stage="guarded_release",
                path=result.path,
                mutation_may_have_occurred=True,
                details={"save_result": result.to_dict()},
            ) from exc
    return FinalizeResult(
        save=result,
        verified_state=verified_state,
        release_result=release_result,
        released=guarded_release is not None,
    )
