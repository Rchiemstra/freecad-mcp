"""Document lease service operations — live evidence."""

from __future__ import annotations

from ..errors.live_document_validation_error import LiveDocumentValidationError
from ..identity import (
    canonicalize_path,
)
from ..model import (
    FileBaseline,
    LeaseRecord,
    LiveDocumentValidation,
)


def _registered_document_failures(
    *,
    registered,
    expected,
    live,
) -> list[str]:
    failures: list[str] = []
    if registered.session_uuid != expected.session_uuid:
        failures.append("registered document session changed")
    if registered.comparison_key != expected.comparison_key:
        failures.append("registered document path changed")
    if registered.file_identity != expected.file_identity:
        failures.append("registered document file identity changed")
    if live.session_uuid != expected.session_uuid:
        failures.append("live document session changed")
    return failures


def _live_document_path_failures(live, *, identity_platform) -> list[str]:
    failures: list[str] = []
    if live.canonical_path:
        try:
            _canonical, comparison = canonicalize_path(
                live.canonical_path, platform=identity_platform
            )
        except Exception:
            failures.append("live document path is invalid")
        else:
            if comparison != live.comparison_key:
                failures.append("live document comparison key is inconsistent")
    elif live.comparison_key is not None:
        failures.append("live document path identity is incomplete")
    return failures


def _baseline_comparison_failures(
    current_baseline: FileBaseline | None,
    expected_baseline: FileBaseline | None,
) -> list[str]:
    if current_baseline == expected_baseline:
        return []
    if expected_baseline is None or current_baseline is None:
        return ["saved file baseline is missing or newly present"]
    failures: list[str] = []
    if current_baseline.file_identity != expected_baseline.file_identity:
        failures.append("saved file identity changed")
    if current_baseline.size != expected_baseline.size:
        failures.append("saved file size changed")
    if current_baseline.mtime_ns != expected_baseline.mtime_ns:
        failures.append("saved file modification time changed")
    if current_baseline.sha256 != expected_baseline.sha256:
        failures.append("saved file hash changed")
    return failures


def _baseline_live_document_failures(
    current_baseline: FileBaseline | None,
    live,
) -> list[str]:
    failures: list[str] = []
    if current_baseline is not None:
        if live.canonical_path is None:
            failures.append("a file baseline was supplied for an unsaved document")
        if current_baseline.file_identity != live.file_identity:
            failures.append("baseline and live document file identities disagree")
    elif live.canonical_path is not None:
        failures.append("saved live document has no current file baseline")
    return failures


def _validate_live_evidence(
    self,
    record: LeaseRecord,
    validation: LiveDocumentValidation,
) -> None:
    """Require fresh document and file evidence to match lease authority."""

    if not isinstance(validation, LiveDocumentValidation):
        raise LiveDocumentValidationError(
            "fresh LiveDocumentValidation evidence is required"
        )

    failures: list[str] = []
    expected = record.document
    live = validation.document
    try:
        registered = self.identity_service.resolve(expected.session_uuid)
    except Exception as exc:
        raise LiveDocumentValidationError(
            "the leased document is no longer registered as open",
            details={"reason": str(exc)},
        ) from exc

    failures.extend(
        _registered_document_failures(
            registered=registered,
            expected=expected,
            live=live,
        )
    )
    failures.extend(
        _live_document_path_failures(
            live,
            identity_platform=self.identity_service.platform,
        )
    )
    if live.comparison_key != expected.comparison_key:
        failures.append("live document path changed")
    if live.file_identity != expected.file_identity:
        failures.append("live document file identity changed")
    if not validation.baseline_validated:
        failures.append("current file/snapshot baseline was not validated")

    failures.extend(
        _baseline_comparison_failures(validation.baseline, record.baseline)
    )
    failures.extend(_baseline_live_document_failures(validation.baseline, live))

    if failures:
        unique_failures = list(dict.fromkeys(failures))
        raise LiveDocumentValidationError(
            "; ".join(unique_failures),
            details={"failures": unique_failures},
        )
