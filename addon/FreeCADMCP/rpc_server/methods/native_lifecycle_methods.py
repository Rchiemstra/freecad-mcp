"""Native FreeCAD save lifecycle RPC methods.

These methods resolve a live document, delegate persistence to FreeCAD, and
verify the resulting live FCStd.  They compare an Unchanged result with the
baseline sampled for that invocation, but create no durable authority sidecar,
hold no credential, and do not decide recovery/lease state.
"""

from __future__ import annotations

import hashlib
import os
import zipfile
from collections.abc import Mapping
from typing import Any

from .cad_methods_ops.mutation_readiness import document_readiness


def _error(code: str, message: str) -> dict[str, Any]:
    return {"success": False, "error_code": code, "error": message}


def _document_path(document: Any, fallback: str = "") -> str:
    return str(getattr(document, "FileName", "") or fallback)


def _resulting_clean(document: Any, fallback: bool = False) -> bool:
    pending = getattr(document, "hasPendingFileChanges", None)
    if callable(pending):
        failure = getattr(document, "lastCanonicalSaveFailed", None)
        failed = bool(failure()) if callable(failure) else False
        return not bool(pending()) and not failed
    state_getter = getattr(document, "getFileChangeState", None)
    if callable(state_getter):
        state = state_getter()
        if isinstance(state, Mapping):
            return bool(state.get("state") == "clean") and not bool(
                state.get("last_canonical_save_failed", False)
            )
    modified = getattr(document, "Modified", None)
    return (not bool(modified)) if modified is not None else bool(fallback)


def _stat_signature(info: os.stat_result) -> tuple[int, int, int, int]:
    return (
        int(info.st_dev),
        int(info.st_ino),
        int(info.st_size),
        int(info.st_mtime_ns),
    )


def _stable_archive_evidence(path: str) -> dict[str, Any]:
    """Hash and validate one stable live FCStd path without claiming lease authority."""

    canonical = os.path.realpath(path)
    path_before = os.stat(canonical)
    digest = hashlib.sha256()
    with open(canonical, "rb") as stream:
        handle_before = os.fstat(stream.fileno())
        if _stat_signature(path_before) != _stat_signature(handle_before):
            raise ValueError("FCStd path changed while verification opened it")
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
        stream.seek(0)
        with zipfile.ZipFile(stream, "r") as archive:
            infos = archive.infolist()
            names = {item.filename for item in infos}
            if "Document.xml" not in names:
                raise ValueError("FCStd archive is missing Document.xml")
            corrupt = archive.testzip()
            if corrupt is not None:
                raise ValueError(f"FCStd archive member is corrupt: {corrupt}")
        handle_after = os.fstat(stream.fileno())
    path_after = os.stat(canonical)
    expected = _stat_signature(path_before)
    if (
        _stat_signature(handle_before) != expected
        or _stat_signature(handle_after) != expected
        or _stat_signature(path_after) != expected
    ):
        raise ValueError("FCStd file changed during archive verification")
    return {
        "canonical_path": canonical,
        "size": int(path_after.st_size),
        "mtime_ns": int(path_after.st_mtime_ns),
        "sha256": digest.hexdigest(),
        "file_identity": {
            "device": int(path_after.st_dev),
            "inode": int(path_after.st_ino),
        },
        "archive": {
            "ok": True,
            "member_count": len(infos),
            "uncompressed_size": sum(int(item.file_size) for item in infos),
            "required_members": ["Document.xml"],
        },
    }


def _evidence_fingerprint(evidence: Mapping[str, Any]) -> tuple[Any, ...]:
    identity = evidence.get("file_identity")
    identity = identity if isinstance(identity, Mapping) else {}
    return (
        evidence.get("sha256"),
        evidence.get("size"),
        evidence.get("mtime_ns"),
        identity.get("device"),
        identity.get("inode"),
    )


def _capture_invocation_baseline(path: str) -> tuple[dict[str, Any] | None, str | None]:
    if not path or not os.path.isfile(os.path.realpath(path)):
        return None, None
    try:
        return _stable_archive_evidence(path), None
    except Exception as exc:
        return None, str(exc)


def _outcome_result(  # noqa: C901
    document: Any,
    outcome: Mapping[str, Any],
    *,
    fallback_path: str = "",
    invocation_baseline: Mapping[str, Any] | None = None,
    invocation_baseline_error: str | None = None,
) -> dict[str, Any]:
    """Normalize native ``*WithOutcome`` dictionaries to the MCP save shape."""

    raw_warnings = outcome.get("warnings")
    if raw_warnings is None:
        native_warnings: list[str] | None = None
    elif not isinstance(raw_warnings, list) or not all(
        isinstance(item, str) for item in raw_warnings
    ):
        return {
            **_error(
                "NATIVE_SAVE_REJECTED",
                "FreeCAD returned invalid save warnings",
            ),
            "document_name": str(getattr(document, "Name", "") or ""),
            "authority": "native_freecad",
        }
    else:
        native_warnings = list(raw_warnings)

    durability_present = "durability_verified" in outcome
    durability_verified = outcome.get("durability_verified")
    if durability_present and not isinstance(durability_verified, bool):
        return {
            **_error(
                "NATIVE_SAVE_REJECTED",
                "FreeCAD returned an invalid save durability result",
            ),
            "document_name": str(getattr(document, "Name", "") or ""),
            "authority": "native_freecad",
        }

    if "save_disposition" in outcome:
        raw_disposition = outcome["save_disposition"]
    elif "disposition" in outcome:
        raw_disposition = outcome["disposition"]
    else:
        raw_disposition = "failed"
    raw_success = outcome.get("success", raw_disposition != "failed")
    raw_file_written = outcome.get("file_written", False)
    raw_unchanged = outcome.get("unchanged", raw_disposition == "unchanged")
    raw_resulting_clean = outcome.get("resulting_clean")
    invalid_scalar = (
        not isinstance(raw_disposition, str)
        or not isinstance(raw_success, bool)
        or not isinstance(raw_file_written, bool)
        or not isinstance(raw_unchanged, bool)
        or (
            raw_resulting_clean is not None
            and not isinstance(raw_resulting_clean, bool)
        )
    )
    disposition = raw_disposition if isinstance(raw_disposition, str) else "failed"
    file_written = raw_file_written if isinstance(raw_file_written, bool) else False
    unchanged = raw_unchanged if isinstance(raw_unchanged, bool) else False
    native_success = raw_success if isinstance(raw_success, bool) else False
    valid_matrix = (
        (
            disposition == "failed"
            and not native_success
            and not unchanged
        )
        or (
            disposition == "unchanged"
            and native_success
            and unchanged
            and not file_written
        )
        or (
            disposition in {"written", "copy_written"}
            and native_success
            and file_written
            and not unchanged
        )
    )
    if invalid_scalar or not valid_matrix:
        return {
            **_error(
                "NATIVE_SAVE_OUTCOME_INCONSISTENT",
                "FreeCAD returned a contradictory native save outcome",
            ),
            "saved": False,
            "save_disposition": disposition,
            "file_written": file_written,
            "unchanged": unchanged,
            "document_name": str(getattr(document, "Name", "") or ""),
            "authority": "native_freecad",
        }
    canonical_path = str(
        outcome.get("canonical_path") or _document_path(document, fallback_path)
    )
    target_path = str(outcome.get("target_path") or fallback_path or canonical_path)
    reported_clean = bool(
        outcome.get("resulting_clean", _resulting_clean(document, fallback=unchanged))
    )
    live_clean = _resulting_clean(document, fallback=reported_clean)
    resulting_clean = reported_clean and live_clean
    message = str(outcome.get("message") or "")
    requires_verified_durability = file_written or disposition in {
        "written",
        "copy_written",
    }
    saved = native_success and (
        (unchanged and disposition == "unchanged")
        or (
            file_written
            and disposition in {"written", "copy_written"}
            and durability_verified is True
        )
    )
    result = {
        "success": native_success,
        "saved": saved,
        "save_disposition": disposition,
        "file_written": file_written,
        "unchanged": unchanged,
        "canonical_path": canonical_path,
        "target_path": target_path,
        "resulting_clean": resulting_clean,
        "reported_clean": reported_clean,
        "live_clean": live_clean,
        "message": message,
        "document_name": str(getattr(document, "Name", "") or ""),
        "authority": "native_freecad",
    }
    if native_warnings is not None:
        result["warnings"] = native_warnings
    if durability_present:
        result["durability_verified"] = durability_verified
    if not result["success"]:
        result.update(
            error_code=str(outcome.get("error_code") or "NATIVE_SAVE_REJECTED"),
            error=message or "FreeCAD rejected the save",
        )
        return result
    if requires_verified_durability and durability_verified is not True:
        result.update(
            success=False,
            saved=False,
            durability_verified=False,
            error_code="DURABILITY_UNVERIFIED",
            error=(
                "FreeCAD did not verify that the written FCStd and its directory entry "
                "are durable; finalization was not released."
            ),
        )
        return result
    verification_path = target_path or canonical_path
    try:
        file_evidence = _stable_archive_evidence(verification_path)
    except Exception as exc:
        result.update(
            success=False,
            saved=False,
            error_code="POST_SAVE_VERIFICATION_FAILED",
            error=f"Saved FCStd could not be verified: {exc}",
        )
        return result
    result["file_evidence"] = file_evidence
    if unchanged:
        if not resulting_clean:
            result.update(
                success=False,
                saved=False,
                error_code="UNCHANGED_SAVE_NOT_CLEAN",
                error="FreeCAD reported an unchanged save but the document remains modified.",
            )
            return result
        if invocation_baseline_error:
            result.update(
                success=False,
                saved=False,
                error_code="UNCHANGED_SAVE_REVALIDATION_FAILED",
                error=(
                    "The pre-save canonical baseline could not be validated: "
                    f"{invocation_baseline_error}"
                ),
            )
            return result
        if invocation_baseline is None:
            result.update(
                success=False,
                saved=False,
                error_code="UNCHANGED_SAVE_BASELINE_UNAVAILABLE",
                error="FreeCAD reported Unchanged without a verifiable pre-save file baseline.",
            )
            return result
        result["invocation_baseline"] = dict(invocation_baseline)
        if _evidence_fingerprint(invocation_baseline) != _evidence_fingerprint(file_evidence):
            result.update(
                success=False,
                saved=False,
                error_code="UNCHANGED_SAVE_BASELINE_CHANGED",
                error="The canonical FCStd changed while FreeCAD reported an unchanged save.",
            )
    return result


def _quarantine_failure(document: Any) -> dict[str, Any] | None:
    """Never persist/release a document whose rollback integrity is unproven."""

    readiness = document_readiness(document)
    if not readiness.get("quarantined") and not readiness.get(
        "collaboration_poisoned"
    ):
        return None
    return {
        **_error(
            "DOCUMENT_QUARANTINED",
            "The document is quarantined after an unverified rollback; close and reopen a "
            "verified archive before saving or finalizing it.",
        ),
        "document_name": str(getattr(document, "Name", "") or ""),
        "mutation_readiness": [readiness],
        "finalized": False,
        "released": False,
    }


def _selector_error(selector: Any) -> dict[str, Any] | None:
    if not isinstance(selector, Mapping):
        return _error("DOCUMENT_NOT_FOUND", "selector did not resolve a live document")
    if str(selector.get("document_session_uuid") or ""):
        return _error(
            "DOCUMENT_SESSION_SELECTOR_DEPRECATED",
            "legacy document_session_uuid selectors do not identify native FreeCAD documents",
        )
    return None


def _resolve_document_gui(facade: Any, selector: Mapping[str, Any]):
    if not isinstance(selector, Mapping):
        return None
    freecad = facade._execution_collaborators.freecad
    documents = tuple(freecad.listDocuments().values())
    resolved: list[Any] = []

    name = str(selector.get("document_name") or "")
    if name:
        document = freecad.getDocument(name)
        if document is None:
            return None
        resolved.append(document)

    requested_path = str(selector.get("canonical_path") or "")
    if requested_path:
        expected = os.path.normcase(os.path.realpath(requested_path))
        matching = []
        for document in documents:
            current = str(getattr(document, "FileName", "") or "")
            if current and os.path.normcase(os.path.realpath(current)) == expected:
                matching.append(document)
        if len(matching) != 1:
            return None
        resolved.append(matching[0])

    if not resolved or any(document is not resolved[0] for document in resolved[1:]):
        return None
    return resolved[0]


def _save_gui(document: Any) -> dict[str, Any]:
    quarantine = _quarantine_failure(document)
    if quarantine is not None:
        return quarantine
    if not str(getattr(document, "FileName", "") or ""):
        return _error("DOCUMENT_HAS_NO_FILE", "Save As is required for this document")
    save_with_outcome = getattr(document, "saveWithOutcome", None)
    if not callable(save_with_outcome):
        return _error(
            "NATIVE_SAVE_OUTCOME_UNAVAILABLE",
            "This FreeCAD runtime cannot prove change-aware save outcomes; update the native "
            "runtime before saving or finalizing through MCP.",
        )
    baseline, baseline_error = _capture_invocation_baseline(
        str(getattr(document, "FileName", "") or "")
    )
    try:
        outcome = save_with_outcome()
    except Exception as exc:
        return _error("NATIVE_SAVE_FAILED", f"FreeCAD save failed: {exc}")
    if not isinstance(outcome, Mapping):
        return _error(
            "NATIVE_SAVE_REJECTED",
            "FreeCAD returned an invalid save outcome",
        )
    return _outcome_result(
        document,
        outcome,
        invocation_baseline=baseline,
        invocation_baseline_error=baseline_error,
    )


def _pending_file_state(document: Any) -> dict[str, Any]:
    state_getter = getattr(document, "getFileChangeState", None)
    if callable(state_getter):
        state = state_getter()
        if isinstance(state, Mapping):
            return dict(state)
    pending = getattr(document, "hasPendingFileChanges", None)
    modified = getattr(document, "Modified", None)
    return {
        "has_pending_file_changes": bool(pending()) if callable(pending) else None,
        "modified": bool(modified) if modified is not None else None,
    }


def _save_copy_gui(  # noqa: C901
    document: Any,
    destination: str,
    overwrite: bool,
) -> dict[str, Any]:
    quarantine = _quarantine_failure(document)
    if quarantine is not None:
        return quarantine
    if not destination:
        return _error("DESTINATION_REQUIRED", "destination is required")
    canonical_before = _document_path(document)
    destination_real = os.path.realpath(str(destination))
    if not overwrite and os.path.isfile(destination_real):
        return _error(
            "DESTINATION_EXISTS",
            "Save Copy refuses to clobber an existing destination when overwrite=False",
        )
    if canonical_before:
        canonical_real = os.path.normcase(os.path.realpath(canonical_before))
        if os.path.normcase(destination_real) == canonical_real:
            return _error(
                "COPY_TARGET_IS_CANONICAL",
                "Save Copy cannot overwrite the canonical document",
            )
    save_copy_with_outcome = getattr(document, "saveCopyWithOutcome", None)
    if not callable(save_copy_with_outcome):
        return _error(
            "NATIVE_SAVE_OUTCOME_UNAVAILABLE",
            "This FreeCAD runtime cannot prove change-aware Save Copy outcomes; update the "
            "native runtime before saving a copy through MCP.",
        )
    pending_before = _pending_file_state(document)
    baseline, baseline_error = _capture_invocation_baseline(canonical_before)
    try:
        outcome = save_copy_with_outcome(str(destination))
    except Exception as exc:
        return _error("NATIVE_SAVE_COPY_FAILED", f"FreeCAD Save Copy failed: {exc}")
    if not isinstance(outcome, Mapping):
        return _error(
            "NATIVE_SAVE_COPY_REJECTED",
            "FreeCAD returned an invalid Save Copy outcome",
        )
    result = _outcome_result(
        document,
        outcome,
        fallback_path=str(destination),
        invocation_baseline=baseline,
        invocation_baseline_error=baseline_error,
    )
    canonical_after = _document_path(document)
    if canonical_before != canonical_after:
        result.update(
            success=False,
            saved=False,
            error_code="CANONICAL_SAVEPOINT_MOVED",
            error=(
                "Save Copy must not move the canonical savepoint; "
                f"FileName changed from {canonical_before!r} to {canonical_after!r}"
            ),
        )
        return result
    if canonical_before:
        before_real = os.path.normcase(os.path.realpath(canonical_before))
        after_real = os.path.normcase(os.path.realpath(canonical_after))
        if before_real != after_real:
            result.update(
                success=False,
                saved=False,
                error_code="CANONICAL_SAVEPOINT_MOVED",
                error="Save Copy must not move the canonical savepoint path",
            )
            return result
    pending_after = _pending_file_state(document)
    if pending_before != pending_after:
        result.update(
            success=False,
            saved=False,
            error_code="CANONICAL_PENDING_STATE_CLEARED",
            error=(
                "Save Copy must not clear canonical pending-file state; "
                "callers may recompute afterward if needed"
            ),
        )
        return result
    return result


def _save_as_gui(
    document: Any,
    destination: str,
    overwrite: bool,
    expected_destination_sha256: str,
) -> dict[str, Any]:
    quarantine = _quarantine_failure(document)
    if quarantine is not None:
        return quarantine
    if not destination:
        return _error("DESTINATION_REQUIRED", "destination is required")
    save_with_outcome = getattr(document, "saveAsWithOutcome", None)
    if not callable(save_with_outcome):
        return _error(
            "NATIVE_SAVE_OUTCOME_UNAVAILABLE",
            "This FreeCAD runtime cannot prove change-aware Save As outcomes; update the "
            "native runtime before saving or finalizing through MCP.",
        )
    baseline, baseline_error = _capture_invocation_baseline(str(destination))
    try:
        if expected_destination_sha256:
            outcome = save_with_outcome(
                str(destination),
                bool(overwrite),
                str(expected_destination_sha256),
            )
        else:
            outcome = save_with_outcome(str(destination), bool(overwrite))
    except TypeError as exc:
        if expected_destination_sha256:
            return _error(
                "EXPECTED_DESTINATION_HASH_UNSUPPORTED",
                "This FreeCAD runtime cannot enforce the expected destination SHA-256; "
                f"update the native runtime before retrying Save As ({exc}).",
            )
        return _error("NATIVE_SAVE_AS_FAILED", f"FreeCAD Save As failed: {exc}")
    except Exception as exc:
        return _error("NATIVE_SAVE_AS_FAILED", f"FreeCAD Save As failed: {exc}")
    if not isinstance(outcome, Mapping):
        return _error(
            "NATIVE_SAVE_AS_REJECTED",
            "FreeCAD returned an invalid Save As outcome",
        )
    return _outcome_result(
        document,
        outcome,
        fallback_path=str(destination),
        invocation_baseline=baseline,
        invocation_baseline_error=baseline_error,
    )


def _resolve_and_save_gui(facade: Any, selector: Mapping[str, Any]) -> dict[str, Any]:
    document = _resolve_document_gui(facade, selector)
    if document is None:
        return _error("DOCUMENT_NOT_FOUND", "selector did not resolve a live document")
    return _save_gui(document)


def _resolve_and_save_as_gui(
    facade: Any,
    selector: Mapping[str, Any],
    destination: str,
    overwrite: bool,
    expected_destination_sha256: str,
) -> dict[str, Any]:
    document = _resolve_document_gui(facade, selector)
    if document is None:
        return _error("DOCUMENT_NOT_FOUND", "selector did not resolve a live document")
    return _save_as_gui(
        document,
        destination,
        overwrite,
        expected_destination_sha256,
    )


def _resolve_and_save_copy_gui(
    facade: Any,
    selector: Mapping[str, Any],
    destination: str,
    overwrite: bool,
) -> dict[str, Any]:
    document = _resolve_document_gui(facade, selector)
    if document is None:
        return _error("DOCUMENT_NOT_FOUND", "selector did not resolve a live document")
    return _save_copy_gui(document, destination, overwrite)


def save_document(self, selector, validation_profile="default"):
    if validation_profile != "default":
        return _error(
            "VALIDATION_PROFILE_UNSUPPORTED",
            "Native FreeCAD persistence does not accept MCP validation profiles",
        )
    selector_failure = _selector_error(selector)
    if selector_failure is not None:
        return selector_failure
    result = self._dispatch_gui(lambda: _resolve_and_save_gui(self, selector))
    return result if isinstance(result, dict) else _error("NATIVE_SAVE_FAILED", str(result))


def save_document_as(
    self,
    selector,
    destination,
    overwrite=False,
    expected_destination_sha256="",
    validation_profile="default",
):
    if validation_profile != "default":
        return _error(
            "VALIDATION_PROFILE_UNSUPPORTED",
            "Native FreeCAD persistence does not accept MCP validation profiles",
        )
    selector_failure = _selector_error(selector)
    if selector_failure is not None:
        return selector_failure
    result = self._dispatch_gui(
        lambda: _resolve_and_save_as_gui(
            self,
            selector,
            destination,
            overwrite,
            expected_destination_sha256,
        )
    )
    return result if isinstance(result, dict) else _error("NATIVE_SAVE_FAILED", str(result))


def save_document_copy(
    self,
    selector,
    destination,
    overwrite=False,
    validation_profile="default",
):
    if validation_profile != "default":
        return _error(
            "VALIDATION_PROFILE_UNSUPPORTED",
            "Native FreeCAD persistence does not accept MCP validation profiles",
        )
    selector_failure = _selector_error(selector)
    if selector_failure is not None:
        return selector_failure
    result = self._dispatch_gui(
        lambda: _resolve_and_save_copy_gui(
            self,
            selector,
            destination,
            overwrite,
        )
    )
    return result if isinstance(result, dict) else _error("NATIVE_SAVE_FAILED", str(result))


def finalize_document_edit(
    self,
    selector,
    save_mode="save",
    destination="",
    overwrite=False,
    expected_destination_sha256="",
    validation_profile="default",
):
    if save_mode == "save":
        result = save_document(self, selector, validation_profile)
    elif save_mode in {"save_as", "first_save"}:
        result = save_document_as(
            self,
            selector,
            destination,
            overwrite,
            expected_destination_sha256,
            validation_profile,
        )
    else:
        return {
            **_error("INVALID_SAVE_MODE", f"Unsupported save_mode: {save_mode}"),
            "finalized": False,
            "released": False,
        }
    if not result.get("success"):
        return {**result, "finalized": False, "released": False}
    if result.get("saved") is not True:
        return {
            **result,
            "success": False,
            "saved": False,
            "error_code": "NATIVE_SAVE_OUTCOME_INCONSISTENT",
            "error": (
                "FreeCAD reported save success without an authoritative saved result; "
                "finalization was not released."
            ),
            "finalized": False,
            "released": False,
        }
    if not result.get("resulting_clean", False):
        return {
            **result,
            "success": False,
            "saved": False,
            "error_code": "DOCUMENT_REMAINS_MODIFIED",
            "error": (
                "FreeCAD did not report a clean document after save; "
                "finalization was not released."
            ),
            "finalized": False,
            "released": False,
        }
    return {
        **result,
        "finalized": True,
        "released": True,
        "release": {"authority": "native_freecad", "lease_present": False},
    }


__all__ = ["finalize_document_edit", "save_document", "save_document_as"]
