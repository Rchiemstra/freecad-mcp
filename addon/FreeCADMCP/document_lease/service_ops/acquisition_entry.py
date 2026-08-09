"""Document lease service operations — acquisition entry."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from .. import service as service_mod
from ..errors.dirty_acquisition_error import DirtyAcquisitionError
from ..errors.dirty_adoption_error import DirtyAdoptionError
from ..errors.lease_grant import LeaseGrant
from ..errors.lease_service_error import LeaseServiceError
from ..identity import DocumentIdentityError
from ..model import (
    DocumentSelector,
    FileBaseline,
    LeaseOwner,
)


def acquire(
    self,
    selector: DocumentSelector | Mapping[str, Any] | str,
    owner: LeaseOwner,
    *,
    task_summary: str = "",
    document_dirty: bool = False,
    baseline: FileBaseline | None = None,
    baseline_validated: bool = False,
    snapshot_id: str | None = None,
) -> LeaseGrant:
    """Reserve first, then capture/validate and promote the acquisition."""

    reservation = self.begin_acquisition(
        selector,
        owner,
        task_summary=task_summary,
        document_dirty=document_dirty,
    )
    try:
        observed_baseline = baseline
        observed_validated = bool(baseline_validated)
        path = reservation.record.document.canonical_path
        if path and observed_baseline is None:
            if not os.path.isfile(path):
                raise LeaseServiceError(
                    "saved document path is missing or is not a regular file"
                )
            try:
                observed_baseline = service_mod.capture_file_baseline(
                    path, platform=self.identity_service.platform
                )
            except (OSError, DocumentIdentityError) as exc:
                raise LeaseServiceError(
                    f"unable to capture document baseline: {exc}"
                ) from exc
            observed_validated = True
        return self.complete_acquisition(
            reservation.credential,
            baseline=observed_baseline,
            baseline_validated=observed_validated,
            snapshot_id=snapshot_id,
        )
    except Exception:
        # No token has escaped and no mutation has begun. Roll back only
        # through an exact CAS; a failed rollback remains visibly locked.
        self.abort_acquisition(reservation.credential)
        raise


def begin_acquisition(
    self,
    selector: DocumentSelector | Mapping[str, Any] | str,
    owner: LeaseOwner,
    *,
    task_summary: str = "",
    document_dirty: bool = False,
    acquisition_request_id: str | None = None,
    live_acquisition_request_ids: frozenset[str] | None = None,
) -> LeaseGrant:
    """Publish ACQUIRING before baseline hashing or snapshot creation."""

    if document_dirty:
        raise DirtyAcquisitionError(
            "a pre-existing dirty document requires local adoption"
        )
    return self._begin_acquisition_record(
        selector,
        owner,
        task_summary=task_summary,
        document_dirty=False,
        replace_unreturned_reservation=True,
        acquisition_request_id=acquisition_request_id,
        live_acquisition_request_ids=live_acquisition_request_ids,
    )


def begin_dirty_adoption(
    self,
    selector: DocumentSelector | Mapping[str, Any] | str,
    owner: LeaseOwner,
    *,
    task_summary: str = "",
    document_dirty: bool,
    local_confirmation: bool,
    acquisition_request_id: str | None = None,
    live_acquisition_request_ids: frozenset[str] | None = None,
) -> LeaseGrant:
    """Reserve a locally confirmed, pre-existing dirty document."""

    if local_confirmation is not True:
        raise DirtyAdoptionError(
            "dirty-document adoption requires explicit local GUI confirmation"
        )
    if document_dirty is not True:
        raise DirtyAdoptionError(
            "dirty-document adoption requires a currently dirty live document"
        )
    return self._begin_acquisition_record(
        selector,
        owner,
        task_summary=task_summary,
        document_dirty=True,
        replace_unreturned_reservation=True,
        acquisition_request_id=acquisition_request_id,
        live_acquisition_request_ids=live_acquisition_request_ids,
    )
