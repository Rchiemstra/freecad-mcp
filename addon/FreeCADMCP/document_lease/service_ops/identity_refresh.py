"""Document lease service operations — identity refresh."""

from __future__ import annotations

import hashlib
import os
from dataclasses import replace
from typing import Any

from ..errors.coordination_error import CoordinationError
from ..errors.document_identity_refresh_event import DocumentIdentityRefreshEvent
from ..errors.lease_service_error import LeaseServiceError
from ..errors.lease_state_error import LeaseStateError
from ..identity import (
    DocumentIdentityError,
    file_identity_for_path,
)
from ..model import (
    DocumentIdentity,
    FileBaseline,
    FileIdentity,
    LeaseRecord,
)
from .constants import (
    IDENTITY_REFRESHABLE_STATES,
    RECOVERY_IDENTITY_REFRESHABLE_STATES,
    bounded_text,
)


def _assert_current_baseline(
    self,
    identity: DocumentIdentity,
    baseline: FileBaseline,
    *,
    error_type: type[LeaseServiceError] = CoordinationError,
) -> None:
    """Revalidate lightweight file metadata after an off-lock hash."""

    path = identity.canonical_path
    if not path or not os.path.isfile(path):
        raise error_type("the saved document path is missing or is not a regular file")
    try:
        info = os.stat(path)
        current_identity = file_identity_for_path(
            path, platform=self.identity_service.platform
        )
    except (DocumentIdentityError, OSError) as exc:
        raise error_type(
            f"the saved document identity cannot be revalidated: {exc}"
        ) from exc
    failures = []
    if int(info.st_size) != baseline.size:
        failures.append("size changed")
    if int(info.st_mtime_ns) != baseline.mtime_ns:
        failures.append("modification time changed")
    if current_identity != baseline.file_identity:
        failures.append("file identity changed")
    if current_identity != identity.file_identity:
        failures.append("registered document identity changed")
    if failures:
        raise error_type(
            "the saved document changed during orphan recovery: " + "; ".join(failures)
        )


def _assert_on_disk_matches_accepted_baseline(
    self,
    path: str,
    baseline: FileBaseline,
    *,
    error_type: type[LeaseServiceError] = CoordinationError,
    allow_file_identity_change: bool = False,
    chunk_size: int = 1024 * 1024,
) -> None:
    """Require the saved file to still match the lease's accepted baseline."""

    if not os.path.isfile(path):
        raise error_type("the saved document path is missing or is not a regular file")
    try:
        info = os.stat(path)
        current_identity = file_identity_for_path(
            path, platform=self.identity_service.platform
        )
    except (DocumentIdentityError, OSError) as exc:
        raise error_type(
            f"the saved document identity cannot be revalidated: {exc}"
        ) from exc
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    sha256 = digest.hexdigest()
    failures: list[str] = []
    if int(info.st_size) != baseline.size:
        failures.append("size changed")
    # Atomic replace-over-save rewrites the file at the same path and
    # changes mtime while size and SHA-256 stay identical.  Content
    # continuity for baseline-preserving identity repair is proven by
    # size + SHA-256, not exact mtime_ns equality.
    if not allow_file_identity_change and int(info.st_mtime_ns) != baseline.mtime_ns:
        failures.append("modification time changed")
    if sha256 != baseline.sha256:
        failures.append("content hash changed")
    if (
        not allow_file_identity_change
        and baseline.file_identity is not None
        and current_identity != baseline.file_identity
    ):
        failures.append("file identity changed")
    if failures:
        raise error_type(
            "the saved document no longer matches the accepted baseline: "
            + "; ".join(failures)
        )


def _record_identity_refresh_event(
    self,
    record: LeaseRecord,
    *,
    trigger: str,
    previous_file_identity: FileIdentity | None,
    refreshed_file_identity: FileIdentity | None,
) -> None:
    baseline = record.baseline
    baseline_sha256 = baseline.sha256 if isinstance(baseline, FileBaseline) else ""
    self._identity_refresh_events.append(
        DocumentIdentityRefreshEvent(
            at=self._utc_clock(),
            trigger=bounded_text(trigger, 128),
            document_session_uuid=record.document.session_uuid,
            document_name=record.document.name,
            canonical_path=record.document.canonical_path,
            lease_state=record.state.value,
            lease_id=record.lease_id,
            generation=record.generation,
            previous_file_identity=(
                previous_file_identity.to_dict()
                if previous_file_identity is not None
                else None
            ),
            refreshed_file_identity=(
                refreshed_file_identity.to_dict()
                if refreshed_file_identity is not None
                else None
            ),
            baseline_sha256=baseline_sha256,
        )
    )


def _refresh_exact_proxy_file_identity(
    self,
    session_uuid: str,
    document: Any,
    record: LeaseRecord,
    *,
    trigger: str,
) -> LeaseRecord:
    """Refresh file identity metadata without revalidating file content."""

    if record.state not in RECOVERY_IDENTITY_REFRESHABLE_STATES:
        raise LeaseStateError(
            "saved-file identity can refresh only after takeover",
            details={"state": record.state.value},
        )
    self._assert_sidecar_matches(record)
    observed = self.identity_service.inspect_registered_document(session_uuid, document)
    expected = record.document
    if (
        observed.name != expected.name
        or observed.comparison_key != expected.comparison_key
    ):
        raise CoordinationError("GUI save changed the document name or canonical path")
    if observed.file_identity == expected.file_identity:
        return record
    refreshed = self.identity_service.refresh_saved_document(document)
    if refreshed.session_uuid != session_uuid:
        raise CoordinationError("saved document identity changed its live session")
    if refreshed == record.document:
        return record
    updated = record.revised(document=refreshed)
    committed = self._commit(record, updated)
    self._record_identity_refresh_event(
        committed,
        trigger=trigger,
        previous_file_identity=expected.file_identity,
        refreshed_file_identity=refreshed.file_identity,
    )
    return committed


def _apply_baseline_preserving_identity_refresh(
    self,
    session_uuid: str,
    document: Any,
    record: LeaseRecord,
    *,
    trigger: str,
) -> LeaseRecord:
    """Refresh registry and lease metadata after a baseline-preserving save."""

    if record.state not in IDENTITY_REFRESHABLE_STATES:
        raise LeaseStateError(
            "saved-file identity cannot refresh in the current lease state",
            details={"state": record.state.value},
        )
    self._assert_sidecar_matches(record)
    baseline = record.baseline
    if not isinstance(baseline, FileBaseline):
        raise CoordinationError("accepted saved-file baseline is missing")
    observed = self.identity_service.inspect_registered_document(session_uuid, document)
    expected = record.document
    if (
        observed.name != expected.name
        or observed.comparison_key != expected.comparison_key
    ):
        raise CoordinationError("GUI save changed the document name or canonical path")
    path = observed.canonical_path
    if not path:
        raise CoordinationError(
            "an unsaved document has no saved-file identity to refresh"
        )
    if observed.file_identity == expected.file_identity:
        return record
    self._assert_on_disk_matches_accepted_baseline(
        path,
        baseline,
        allow_file_identity_change=True,
    )
    refreshed = self.identity_service.refresh_saved_document(document)
    if refreshed.session_uuid != session_uuid:
        raise CoordinationError("saved document identity changed its live session")
    if (
        refreshed.name != observed.name
        or refreshed.comparison_key != observed.comparison_key
        or refreshed.file_identity != observed.file_identity
    ):
        raise CoordinationError(
            "saved document identity refresh changed the live document binding"
        )
    if refreshed == record.document:
        return record
    post_rewrite_mtime_ns = int(os.stat(path).st_mtime_ns)
    refreshed_baseline = replace(
        baseline,
        file_identity=refreshed.file_identity,
        mtime_ns=post_rewrite_mtime_ns,
    )
    updated = record.revised(document=refreshed, baseline=refreshed_baseline)
    committed = self._commit(record, updated)
    self._record_identity_refresh_event(
        committed,
        trigger=trigger,
        previous_file_identity=expected.file_identity,
        refreshed_file_identity=refreshed.file_identity,
    )
    return committed
