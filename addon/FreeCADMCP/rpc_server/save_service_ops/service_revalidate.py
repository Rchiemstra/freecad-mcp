"""SaveService extracted methods."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from typing import Any

from ..save_types.document_dirty_error import DocumentDirtyError
from ..save_types.invalid_save_request_error import InvalidSaveRequestError
from ..save_types.save_invocation import SaveInvocation
from ..save_types.save_invocation_error import SaveInvocationError
from ..save_types.save_service_error import SaveServiceError

try:
    from document_lease.identity import (
        DocumentIdentityError,
                file_identity_for_path,
    )
    from document_lease.model import FileBaseline
except ImportError:
    from addon.FreeCADMCP.document_lease.identity import (
        DocumentIdentityError,
        file_identity_for_path,
    )
    from addon.FreeCADMCP.document_lease.model import FileBaseline

from .baseline import (
    _identity_dict,
)
from .document_state import (
    _document_filename,
    _document_is_dirty,
)
from .service_preflight import canonical_path

DomainValidator = Callable[[str, str], Mapping[str, Any] | bool | None]
DestinationGuardFactory = Callable[[str], AbstractContextManager[Any]]


def revalidate_file_metadata(
    service,
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
            path, platform=service.platform
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

def assert_document_path_gui(
    service,
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
    live_canonical, live_comparison = canonical_path(service, live_path)
    if live_comparison != expected_comparison_key:
        raise SaveInvocationError(
            "FreeCAD document is bound to an unexpected path",
            stage="document_identity_check",
            path=live_canonical,
            mutation_may_have_occurred=mutation_may_have_occurred,
            details={"expected_path": expected_path},
        )
    return live_canonical

def invoke_save(service, document: Any, path: str) -> None:
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

def invoke_save_as(service, document: Any, destination: str) -> None:
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

def capture_save_invocation_gui(
    service,
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

    live_canonical = assert_document_path_gui(service, 
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
