"""Baseline comparison helpers for typed FCStd saves."""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from typing import Any

from ..save_types.baseline_mismatch_error import BaselineMismatchError
from ..save_types.baseline_required_error import BaselineRequiredError
from ..save_types.invalid_save_request_error import InvalidSaveRequestError
from ..save_types.saved_file_unstable_error import SavedFileUnstableError

try:
    from document_lease.identity import (
        DocumentIdentityError,
        canonicalize_path,
        capture_file_baseline,
    )
    from document_lease.model import FileBaseline, FileIdentity
except ImportError:
    from addon.FreeCADMCP.document_lease.identity import (
        DocumentIdentityError,
        canonicalize_path,
        capture_file_baseline,
    )
    from addon.FreeCADMCP.document_lease.model import FileBaseline, FileIdentity

_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


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
    if expected_identity is not None and (
        actual_identity is None
        or expected_identity.comparison_tuple()
        != actual_identity.comparison_tuple()
    ):
        differences["file_identity"] = {
            "expected": _identity_dict(expected_identity),
            "actual": _identity_dict(actual_identity),
        }
    return differences


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


def compare_serialized_file_to_baseline(
    path: str | os.PathLike[str],
    expected: dict[str, Any] | None,
    *,
    platform: str | None = None,
    baseline_reader: Callable[..., Any] = capture_file_baseline,
):
    """Compare a public baseline payload without exporting its authority type."""

    canonical, _ = canonicalize_path(path, platform=platform)
    required = {"size", "mtime_ns", "sha256"}
    if not isinstance(expected, dict) or not required.issubset(expected):
        raise BaselineRequiredError(
            "a complete FileBaseline is required",
            stage="preflight",
            path=canonical,
        )
    expected_sha = str(expected["sha256"]).lower()
    if not _SHA256_RE.fullmatch(expected_sha):
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

    try:
        actual_values = {
            "size": actual.size,
            "mtime_ns": actual.mtime_ns,
            "sha256": str(actual.sha256).lower(),
        }
    except (AttributeError, TypeError, ValueError) as exc:
        raise BaselineMismatchError(
            "unable to verify the current file baseline",
            stage="preflight",
            path=canonical,
        ) from exc

    differences: dict[str, dict[str, Any]] = {}
    expected_values = {
        "size": expected["size"],
        "mtime_ns": expected["mtime_ns"],
        "sha256": expected_sha,
    }
    for field_name, expected_value in expected_values.items():
        actual_value = actual_values[field_name]
        if expected_value != actual_value:
            differences[field_name] = {
                "expected": expected_value,
                "actual": actual_value,
            }
    expected_identity = expected.get("file_identity")
    actual_identity = _identity_dict(getattr(actual, "file_identity", None))
    if expected_identity is not None and expected_identity != actual_identity:
        differences["file_identity"] = {
            "expected": expected_identity,
            "actual": actual_identity,
        }
    if differences:
        raise BaselineMismatchError(
            "document file changed since the accepted baseline",
            stage="preflight",
            path=canonical,
            details={"differences": differences},
        )
    return actual
