"""Typed, fail-closed FCStd save and finalization helpers.

The public functions in this module deliberately have no import-time FreeCAD
dependency.  A live ``App::Document`` proxy is supplied by the RPC layer after
the request has been authorized and revalidated on FreeCAD's GUI thread.

This service owns filesystem preflight and post-save verification.  It does
not own lease state: callers should enter ``LOCKED_SAVING`` before invoking it,
record any :class:`SaveServiceError` as ``LOCKED_ERROR``, and pass lease-owned
callbacks to :meth:`SaveService.finalize_document_edit` when a verified save
should be followed by guarded release.
"""

from __future__ import annotations

import contextlib
import hmac
import os
import re
import zipfile
from dataclasses import dataclass, field
from typing import Any, Callable, ContextManager, Mapping

try:
    from document_state import (
        DocumentDirtyStateUnavailable,
        document_modified_state,
        gui_document_for,
        require_document_modified,
        set_document_modified,
    )
except ImportError:
    from addon.FreeCADMCP.document_state import (
        DocumentDirtyStateUnavailable,
        document_modified_state,
        gui_document_for,
        require_document_modified,
        set_document_modified,
    )

try:  # Installed FreeCAD addon: FreeCADMCP itself is on sys.path.
    from document_lease.identity import (
        DocumentIdentityError,
        canonicalize_path,
        capture_file_baseline,
        file_identity_for_path,
    )
    from document_lease.model import FileBaseline, FileIdentity
except ImportError:  # Repository/unit-test namespace import.
    from addon.FreeCADMCP.document_lease.identity import (
        DocumentIdentityError,
        canonicalize_path,
        capture_file_baseline,
        file_identity_for_path,
    )
    from addon.FreeCADMCP.document_lease.model import FileBaseline, FileIdentity


_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_DEFAULT_REQUIRED_MEMBERS = ("Document.xml",)


class SaveServiceError(RuntimeError):
    """Structured save failure suitable for an RPC error response."""

    code = "SAVE_SERVICE_ERROR"

    def __init__(
        self,
        message: str,
        *,
        stage: str,
        path: str | None = None,
        mutation_may_have_occurred: bool = False,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        self.stage = stage
        self.path = path
        self.mutation_may_have_occurred = bool(mutation_may_have_occurred)
        self.details = dict(details or {})
        super().__init__(message)

    def to_dict(self, *, request_id: str | None = None) -> dict[str, Any]:
        error: dict[str, Any] = {
            "code": self.code,
            "message": str(self),
            "stage": self.stage,
            "mutation_may_have_occurred": self.mutation_may_have_occurred,
            "details": dict(self.details),
        }
        if self.path is not None:
            error["path"] = self.path
        if request_id:
            error["request_id"] = request_id
        return error


class InvalidSaveRequestError(SaveServiceError):
    code = "INVALID_SAVE_REQUEST"


class BaselineRequiredError(SaveServiceError):
    code = "BASELINE_REQUIRED"


class BaselineMismatchError(SaveServiceError):
    code = "BASELINE_MISMATCH"


class DestinationConflictError(SaveServiceError):
    code = "SAVE_AS_DESTINATION_CONFLICT"


class SaveInvocationError(SaveServiceError):
    code = "FREECAD_SAVE_FAILED"


class DocumentDirtyError(SaveServiceError):
    code = "DOCUMENT_REMAINS_DIRTY"


class SavedFileUnstableError(SaveServiceError):
    code = "SAVED_FILE_UNSTABLE"


class FcstdVerificationError(SaveServiceError):
    code = "FCSTD_VERIFICATION_FAILED"


class DomainValidationError(SaveServiceError):
    code = "SAVE_DOMAIN_VALIDATION_FAILED"


class LifecycleCallbackError(SaveServiceError):
    code = "SAVE_LIFECYCLE_CALLBACK_FAILED"


@dataclass(frozen=True)
class ArchiveVerification:
    member_count: int
    uncompressed_size: int
    required_members: tuple[str, ...] = _DEFAULT_REQUIRED_MEMBERS

    def to_dict(self) -> dict[str, Any]:
        return {
            "member_count": self.member_count,
            "uncompressed_size": self.uncompressed_size,
            "required_members": list(self.required_members),
        }


@dataclass(frozen=True)
class SaveResult:
    """Authoritative result returned only after the saved FCStd was verified."""

    mode: str
    path: str
    previous_path: str | None
    baseline: FileBaseline
    archive: ArchiveVerification
    validation_profile: str = "default"
    domain_validation: Mapping[str, Any] = field(default_factory=dict)
    destination_preexisted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": True,
            "mode": self.mode,
            "path": self.path,
            "previous_path": self.previous_path,
            "baseline": self.baseline.to_dict(),
            "archive": self.archive.to_dict(),
            "validation_profile": self.validation_profile,
            "domain_validation": dict(self.domain_validation),
            "destination_preexisted": self.destination_preexisted,
        }


@dataclass(frozen=True)
class SaveInvocation:
    """GUI-thread result captured immediately after FreeCAD writes the file."""

    mode: str
    path: str
    comparison_key: str
    previous_path: str | None
    validation_profile: str = "default"
    destination_preexisted: bool = False


@dataclass(frozen=True)
class SavePreflight:
    """Filesystem evidence captured outside FreeCAD's GUI thread."""

    mode: str
    path: str
    comparison_key: str
    previous_path: str | None
    previous_comparison_key: str | None
    source_baseline: FileBaseline | None
    validation_profile: str = "default"
    destination_preexisted: bool = False
    destination_baseline: FileBaseline | None = None


@dataclass(frozen=True)
class FinalizeResult:
    save: SaveResult
    verified_state: Any = None
    release_result: Any = None
    released: bool = False

    def to_dict(self) -> dict[str, Any]:
        result = {
            "ok": True,
            "save": self.save.to_dict(),
            "released": self.released,
        }
        if isinstance(self.verified_state, Mapping):
            result["verified_state"] = dict(self.verified_state)
        if isinstance(self.release_result, Mapping):
            result["release"] = dict(self.release_result)
        return result


def _identity_dict(identity: FileIdentity | None) -> dict[str, Any] | None:
    return identity.to_dict() if identity else None


def _baseline_differences(
    expected: FileBaseline, actual: FileBaseline
) -> dict[str, dict[str, Any]]:
    differences: dict[str, dict[str, Any]] = {}
    for field_name in ("size", "mtime_ns", "sha256"):
        expected_value = getattr(expected, field_name)
        actual_value = getattr(actual, field_name)
        if field_name == "sha256":
            expected_value = str(expected_value).lower()
            actual_value = str(actual_value).lower()
        if expected_value != actual_value:
            differences[field_name] = {
                "expected": expected_value,
                "actual": actual_value,
            }
    expected_identity = expected.file_identity
    actual_identity = actual.file_identity
    if expected_identity is not None:
        if (
            actual_identity is None
            or expected_identity.comparison_tuple()
            != actual_identity.comparison_tuple()
        ):
            differences["file_identity"] = {
                "expected": _identity_dict(expected_identity),
                "actual": _identity_dict(actual_identity),
            }
    return differences


def verify_fcstd_archive(
    path: str | os.PathLike[str],
    *,
    required_members: tuple[str, ...] = _DEFAULT_REQUIRED_MEMBERS,
) -> ArchiveVerification:
    """Fully read an FCStd ZIP and require its core document member."""

    canonical, _ = canonicalize_path(path)
    try:
        with zipfile.ZipFile(canonical, "r") as archive:
            infos = archive.infolist()
            names = {item.filename for item in infos}
            missing = [name for name in required_members if name not in names]
            if missing:
                raise FcstdVerificationError(
                    "saved archive is missing required FCStd members",
                    stage="archive_verification",
                    path=canonical,
                    mutation_may_have_occurred=True,
                    details={"missing_members": missing},
                )
            corrupt_member = archive.testzip()
            if corrupt_member is not None:
                raise FcstdVerificationError(
                    "saved archive contains a corrupt member",
                    stage="archive_verification",
                    path=canonical,
                    mutation_may_have_occurred=True,
                    details={"corrupt_member": corrupt_member},
                )
            return ArchiveVerification(
                member_count=len(infos),
                uncompressed_size=sum(int(item.file_size) for item in infos),
                required_members=required_members,
            )
    except SaveServiceError:
        raise
    except (OSError, RuntimeError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise FcstdVerificationError(
            f"saved file is not a readable FCStd archive: {exc}",
            stage="archive_verification",
            path=canonical,
            mutation_may_have_occurred=True,
        ) from exc


def compare_file_to_baseline(
    path: str | os.PathLike[str],
    expected: FileBaseline,
    *,
    platform: str | None = None,
    baseline_reader: Callable[..., FileBaseline] = capture_file_baseline,
) -> FileBaseline:
    """Capture and compare path identity, stat metadata, and full SHA-256."""

    canonical, _ = canonicalize_path(path, platform=platform)
    if not isinstance(expected, FileBaseline):
        raise BaselineRequiredError(
            "a complete FileBaseline is required",
            stage="preflight",
            path=canonical,
        )
    if not _SHA256_RE.fullmatch(expected.sha256):
        raise InvalidSaveRequestError(
            "expected baseline has an invalid SHA-256",
            stage="preflight",
            path=canonical,
        )
    try:
        actual = baseline_reader(canonical, platform=platform)
    except (OSError, DocumentIdentityError) as exc:
        raise BaselineMismatchError(
            f"unable to verify the current file baseline: {exc}",
            stage="preflight",
            path=canonical,
        ) from exc
    differences = _baseline_differences(expected, actual)
    if differences:
        raise BaselineMismatchError(
            "document file changed since the accepted baseline",
            stage="preflight",
            path=canonical,
            details={"differences": differences},
        )
    return actual


def _call_baseline_reader(
    reader: Callable[..., FileBaseline],
    path: str,
    *,
    platform: str | None,
    mutation_may_have_occurred: bool,
) -> FileBaseline:
    try:
        result = reader(path, platform=platform)
    except (OSError, DocumentIdentityError) as exc:
        raise SavedFileUnstableError(
            f"saved file could not be hashed without a concurrent change: {exc}",
            stage="post_save_hash",
            path=path,
            mutation_may_have_occurred=mutation_may_have_occurred,
        ) from exc
    if not isinstance(result, FileBaseline) or not _SHA256_RE.fullmatch(
        result.sha256
    ):
        raise SavedFileUnstableError(
            "saved file baseline reader returned invalid data",
            stage="post_save_hash",
            path=path,
            mutation_may_have_occurred=mutation_may_have_occurred,
        )
    return result


def _document_filename(document: Any) -> str | None:
    value = getattr(document, "FileName", None)
    if not value:
        return None
    return str(value)


def _document_is_dirty(document: Any) -> bool:
    return require_document_modified(document)


def _clear_document_modified_after_save(document: Any) -> None:
    """Mirror Gui::Document save commands after direct App save calls."""

    try:
        set_document_modified(document, False)
    except DocumentDirtyStateUnavailable:
        if gui_document_for(document) is not None:
            raise
        # Compatibility App fakes clear their own flag.  Preserve a true flag
        # so the subsequent strict check raises DocumentDirtyError rather than
        # masking a simulated save that remained dirty.
        if document_modified_state(document) is None:
            raise


DomainValidator = Callable[[str, str], Mapping[str, Any] | bool | None]
DestinationGuardFactory = Callable[[str], ContextManager[Any]]


class SaveService:
    """Perform typed GUI-thread saves with authoritative file verification."""

    def __init__(
        self,
        *,
        platform: str | None = None,
        baseline_reader: Callable[..., FileBaseline] = capture_file_baseline,
        archive_verifier: Callable[..., ArchiveVerification] = verify_fcstd_archive,
        domain_validator: DomainValidator | None = None,
    ) -> None:
        self.platform = platform
        self._baseline_reader = baseline_reader
        self._archive_verifier = archive_verifier
        self._domain_validator = domain_validator

    def _canonical(self, path: str | os.PathLike[str]) -> tuple[str, str]:
        try:
            return canonicalize_path(path, platform=self.platform)
        except (OSError, DocumentIdentityError, TypeError, ValueError) as exc:
            raise InvalidSaveRequestError(
                f"invalid save path: {exc}", stage="request_validation"
            ) from exc

    def _preflight_source_path(
        self,
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
        canonical, comparison = self._canonical(source_path)
        if expected_path is not None:
            asserted, asserted_comparison = self._canonical(expected_path)
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
            platform=self.platform,
            baseline_reader=self._baseline_reader,
        )
        return canonical, comparison, observed

    def prepare_save(
        self,
        source_path: str | os.PathLike[str] | None,
        *,
        expected_baseline: FileBaseline,
        expected_path: str | os.PathLike[str] | None = None,
        validation_profile: str = "default",
    ) -> SavePreflight:
        """Perform the full compare-before-save hash off the GUI thread."""

        canonical, comparison, observed = self._preflight_source_path(
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
        self,
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

        canonical_destination, destination_comparison = self._canonical(destination)
        parent = os.path.dirname(canonical_destination) or os.curdir
        if not os.path.isdir(parent):
            raise InvalidSaveRequestError(
                "Save As destination parent does not exist",
                stage="destination_preflight",
                path=canonical_destination,
            )
        source, source_comparison, observed_source = self._preflight_source_path(
            source_path,
            expected_baseline=source_baseline,
            required=False,
        )
        destination_preexisted, observed_destination = (
            self._preflight_destination(
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

    def _revalidate_file_metadata(
        self,
        path: str,
        baseline: FileBaseline | None,
        *,
        role: str,
        error_type: type[SaveServiceError],
    ) -> None:
        """Recheck stat/file identity without hashing immediately before save."""

        exists = os.path.lexists(path)
        if baseline is None:
            if exists:
                raise error_type(
                    f"{role} appeared after filesystem preflight",
                    stage="gui_pre_save_revalidation",
                    path=path,
                    details={"role": role},
                )
            return
        if not exists or not os.path.isfile(path):
            raise error_type(
                f"{role} disappeared or is no longer a regular file",
                stage="gui_pre_save_revalidation",
                path=path,
                details={"role": role},
            )
        try:
            info = os.stat(path)
            actual_identity = file_identity_for_path(
                path, platform=self.platform
            )
        except (OSError, DocumentIdentityError) as exc:
            raise error_type(
                f"unable to revalidate {role}: {exc}",
                stage="gui_pre_save_revalidation",
                path=path,
                details={"role": role},
            ) from exc
        differences: dict[str, dict[str, Any]] = {}
        if int(info.st_size) != baseline.size:
            differences["size"] = {
                "expected": baseline.size,
                "actual": int(info.st_size),
            }
        if int(info.st_mtime_ns) != baseline.mtime_ns:
            differences["mtime_ns"] = {
                "expected": baseline.mtime_ns,
                "actual": int(info.st_mtime_ns),
            }
        if baseline.file_identity is not None and (
            actual_identity is None
            or actual_identity.comparison_tuple()
            != baseline.file_identity.comparison_tuple()
        ):
            differences["file_identity"] = {
                "expected": _identity_dict(baseline.file_identity),
                "actual": _identity_dict(actual_identity),
            }
        if differences:
            raise error_type(
                f"{role} changed after filesystem preflight",
                stage="gui_pre_save_revalidation",
                path=path,
                details={"role": role, "differences": differences},
            )

    def _assert_document_path_gui(
        self,
        document: Any,
        *,
        expected_path: str | None,
        expected_comparison_key: str | None,
        require_clean: bool,
        mutation_may_have_occurred: bool,
    ) -> str | None:
        if require_clean and _document_is_dirty(document):
            raise DocumentDirtyError(
                "FreeCAD still reports the document as modified after save",
                stage="document_clean_check",
                path=expected_path,
                mutation_may_have_occurred=mutation_may_have_occurred,
            )
        live_path = _document_filename(document)
        if expected_path is None:
            if live_path is not None:
                raise InvalidSaveRequestError(
                    "FreeCAD document acquired a path before Save As",
                    stage="document_identity_check",
                    path=live_path,
                    mutation_may_have_occurred=mutation_may_have_occurred,
                )
            return None
        if live_path is None:
            raise SaveInvocationError(
                "FreeCAD cleared Document.FileName during save",
                stage="document_identity_check",
                path=expected_path,
                mutation_may_have_occurred=mutation_may_have_occurred,
            )
        live_canonical, live_comparison = self._canonical(live_path)
        if live_comparison != expected_comparison_key:
            raise SaveInvocationError(
                "FreeCAD document is bound to an unexpected path",
                stage="document_identity_check",
                path=live_canonical,
                mutation_may_have_occurred=mutation_may_have_occurred,
                details={"expected_path": expected_path},
            )
        return live_canonical

    def _invoke_save(self, document: Any, path: str) -> None:
        save = getattr(document, "save", None)
        if not callable(save):
            raise InvalidSaveRequestError(
                "document does not expose save()",
                stage="save_invocation",
                path=path,
            )
        try:
            result = save()
        except Exception as exc:
            raise SaveInvocationError(
                f"FreeCAD Document.save() failed: {exc}",
                stage="save_invocation",
                path=path,
                mutation_may_have_occurred=True,
            ) from exc
        if result is False:
            raise SaveInvocationError(
                "FreeCAD Document.save() reported failure",
                stage="save_invocation",
                path=path,
                mutation_may_have_occurred=True,
            )

    def _invoke_save_as(self, document: Any, destination: str) -> None:
        save_as = getattr(document, "saveAs", None)
        if not callable(save_as):
            raise InvalidSaveRequestError(
                "document does not expose saveAs(destination)",
                stage="save_invocation",
                path=destination,
            )
        try:
            result = save_as(destination)
        except Exception as exc:
            raise SaveInvocationError(
                f"FreeCAD Document.saveAs() failed: {exc}",
                stage="save_invocation",
                path=destination,
                mutation_may_have_occurred=True,
            ) from exc
        if result is False:
            raise SaveInvocationError(
                "FreeCAD Document.saveAs() reported failure",
                stage="save_invocation",
                path=destination,
                mutation_may_have_occurred=True,
            )

    def _capture_save_invocation_gui(
        self,
        document: Any,
        *,
        path: str,
        expected_comparison_key: str,
        mode: str,
        previous_path: str | None,
        validation_profile: str,
        destination_preexisted: bool,
    ) -> SaveInvocation:
        """Check only live-proxy facts that must be read on FreeCAD's GUI thread."""

        live_canonical = self._assert_document_path_gui(
            document,
            expected_path=path,
            expected_comparison_key=expected_comparison_key,
            require_clean=True,
            mutation_may_have_occurred=True,
        )
        assert live_canonical is not None
        return SaveInvocation(
            mode=mode,
            path=live_canonical,
            comparison_key=expected_comparison_key,
            previous_path=previous_path,
            validation_profile=validation_profile,
            destination_preexisted=destination_preexisted,
        )

    def verify_saved_file(
        self,
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
            self._baseline_reader,
            live_canonical,
            platform=self.platform,
            mutation_may_have_occurred=True,
        )
        try:
            archive = self._archive_verifier(live_canonical)
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
        validator = domain_validator or self._domain_validator
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
            self._baseline_reader,
            live_canonical,
            platform=self.platform,
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
        self, document: Any, result: SaveResult
    ) -> None:
        """Perform the final lightweight GUI-thread identity/dirty check.

        Full hashing and archive/domain validation have already completed on
        the RPC caller thread.  This check compares path, filesystem identity,
        size, and mtime so a change during the handoff blocks promotion without
        reintroducing expensive GUI-thread I/O.
        """

        canonical, comparison = self._canonical(result.path)
        self._capture_save_invocation_gui(
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
            canonical, platform=self.platform
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
        self,
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
        invocation = self._capture_save_invocation_gui(
            document,
            path=path,
            expected_comparison_key=expected_comparison_key,
            mode=mode,
            previous_path=previous_path,
            validation_profile=validation_profile,
            destination_preexisted=destination_preexisted,
        )
        result = self.verify_saved_file(
            invocation, domain_validator=domain_validator
        )
        self.revalidate_saved_document_gui(document, result)
        return result

    def invoke_save_gui(
        self,
        document: Any,
        preflight: SavePreflight,
    ) -> SaveInvocation:
        """Revalidate lightweight evidence and call ``Document.save`` on GUI."""

        if not isinstance(preflight, SavePreflight) or preflight.mode != "save":
            raise InvalidSaveRequestError(
                "a same-path SavePreflight is required",
                stage="request_validation",
            )
        self._assert_document_path_gui(
            document,
            expected_path=preflight.previous_path,
            expected_comparison_key=preflight.previous_comparison_key,
            require_clean=False,
            mutation_may_have_occurred=False,
        )
        self._revalidate_file_metadata(
            preflight.path,
            preflight.source_baseline,
            role="save source",
            error_type=BaselineMismatchError,
        )
        self._invoke_save(document, preflight.path)
        _clear_document_modified_after_save(document)
        return self._capture_save_invocation_gui(
            document,
            path=preflight.path,
            expected_comparison_key=preflight.comparison_key,
            mode="save",
            previous_path=preflight.previous_path,
            validation_profile=preflight.validation_profile,
            destination_preexisted=True,
        )

    def invoke_save_as_gui(
        self,
        document: Any,
        preflight: SavePreflight,
    ) -> SaveInvocation:
        """Revalidate preflight metadata and call ``saveAs`` on the GUI thread."""

        if not isinstance(preflight, SavePreflight) or preflight.mode != "save_as":
            raise InvalidSaveRequestError(
                "a Save As SavePreflight is required",
                stage="request_validation",
            )
        self._assert_document_path_gui(
            document,
            expected_path=preflight.previous_path,
            expected_comparison_key=preflight.previous_comparison_key,
            require_clean=False,
            mutation_may_have_occurred=False,
        )
        if preflight.previous_path is not None:
            self._revalidate_file_metadata(
                preflight.previous_path,
                preflight.source_baseline,
                role="save source",
                error_type=BaselineMismatchError,
            )
        self._revalidate_file_metadata(
            preflight.path,
            preflight.destination_baseline,
            role="Save As destination",
            error_type=DestinationConflictError,
        )
        self._invoke_save_as(document, preflight.path)
        _clear_document_modified_after_save(document)
        return self._capture_save_invocation_gui(
            document,
            path=preflight.path,
            expected_comparison_key=preflight.comparison_key,
            mode="save_as",
            previous_path=preflight.previous_path,
            validation_profile=preflight.validation_profile,
            destination_preexisted=preflight.destination_preexisted,
        )

    def save_document(
        self,
        document: Any,
        *,
        expected_baseline: FileBaseline,
        expected_path: str | os.PathLike[str] | None = None,
        validation_profile: str = "default",
        domain_validator: DomainValidator | None = None,
    ) -> SaveResult:
        """Compare-before-save, call ``Document.save()``, and verify FCStd."""

        preflight = self.prepare_save(
            _document_filename(document),
            expected_baseline=expected_baseline,
            expected_path=expected_path,
            validation_profile=validation_profile,
        )
        invocation = self.invoke_save_gui(document, preflight)
        result = self.verify_saved_file(
            invocation,
            domain_validator=domain_validator,
        )
        self.revalidate_saved_document_gui(document, result)
        return result

    def _preflight_destination(
        self,
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
            actual = self._baseline_reader(destination, platform=self.platform)
        except (OSError, DocumentIdentityError) as exc:
            raise DestinationConflictError(
                f"unable to verify Save As destination: {exc}",
                stage="destination_preflight",
                path=destination,
            ) from exc
        if expected_destination_baseline is not None:
            differences = _baseline_differences(expected_destination_baseline, actual)
            if differences:
                raise DestinationConflictError(
                    "Save As destination changed since it was inspected",
                    stage="destination_preflight",
                    path=destination,
                    details={"differences": differences},
                )
        if expected_destination_sha256 is not None:
            if not _SHA256_RE.fullmatch(expected_destination_sha256):
                raise InvalidSaveRequestError(
                    "expected destination SHA-256 is invalid",
                    stage="destination_preflight",
                    path=destination,
                )
            if not hmac.compare_digest(
                actual.sha256.lower(), expected_destination_sha256.lower()
            ):
                raise DestinationConflictError(
                    "Save As destination hash changed",
                    stage="destination_preflight",
                    path=destination,
                    details={
                        "expected_sha256": expected_destination_sha256.lower(),
                        "actual_sha256": actual.sha256.lower(),
                    },
                )
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
        if source_comparison_key is not None:
            _, destination_comparison = self._canonical(destination)
            if destination_comparison == source_comparison_key:
                raise DestinationConflictError(
                    "Save As destination is the current document path",
                    stage="destination_preflight",
                    path=destination,
                )
        return True, actual

    def save_document_as(
        self,
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

        canonical_destination, _destination_comparison = self._canonical(destination)
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
                preflight = self.prepare_save_as(
                    source_path,
                    canonical_destination,
                    source_baseline=source_baseline,
                    overwrite=overwrite,
                    expected_destination_sha256=expected_destination_sha256,
                    expected_destination_baseline=expected_destination_baseline,
                    validation_profile=validation_profile,
                )
                save_started = True
                invocation = self.invoke_save_as_gui(document, preflight)
                result = self.verify_saved_file(
                    invocation,
                    domain_validator=domain_validator,
                )
                self.revalidate_saved_document_gui(document, result)
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
        self,
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
            result = self.save_document(
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
            result = self.save_document_as(
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


__all__ = [
    "ArchiveVerification",
    "BaselineMismatchError",
    "BaselineRequiredError",
    "DestinationConflictError",
    "DocumentDirtyError",
    "DomainValidationError",
    "FcstdVerificationError",
    "FinalizeResult",
    "InvalidSaveRequestError",
    "LifecycleCallbackError",
    "SaveInvocationError",
    "SaveInvocation",
    "SavePreflight",
    "SaveResult",
    "SaveService",
    "SaveServiceError",
    "SavedFileUnstableError",
    "compare_file_to_baseline",
    "verify_fcstd_archive",
]
