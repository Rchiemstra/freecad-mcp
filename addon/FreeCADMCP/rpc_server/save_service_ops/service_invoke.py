"""SaveService extracted methods."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from typing import Any

from ..save_types.baseline_mismatch_error import BaselineMismatchError
from ..save_types.destination_conflict_error import DestinationConflictError
from ..save_types.invalid_save_request_error import InvalidSaveRequestError
from ..save_types.save_invocation import SaveInvocation
from ..save_types.save_preflight import SavePreflight
from ..save_types.save_result import SaveResult

try:
    from document_lease.model import FileBaseline
except ImportError:
    from addon.FreeCADMCP.document_lease.model import FileBaseline

from .document_state import (
    _clear_document_modified_after_save,
    _document_filename,
)
from .service_revalidate import (
    assert_document_path_gui,
    capture_save_invocation_gui,
    invoke_save,
    invoke_save_as,
    revalidate_file_metadata,
)

DomainValidator = Callable[[str, str], Mapping[str, Any] | bool | None]
DestinationGuardFactory = Callable[[str], AbstractContextManager[Any]]


def invoke_save_gui(
    service,
    document: Any,
    preflight: SavePreflight,
) -> SaveInvocation:
    """Revalidate lightweight evidence and call ``Document.save`` on GUI."""

    if not isinstance(preflight, SavePreflight) or preflight.mode != "save":
        raise InvalidSaveRequestError(
            "a same-path SavePreflight is required",
            stage="request_validation",
        )
    assert_document_path_gui(service, 
        document,
        expected_path=preflight.previous_path,
        expected_comparison_key=preflight.previous_comparison_key,
        require_clean=False,
        mutation_may_have_occurred=False,
    )
    revalidate_file_metadata(service, 
        preflight.path,
        preflight.source_baseline,
        role="save source",
        error_type=BaselineMismatchError,
    )
    invoke_save(service, document, preflight.path)
    _clear_document_modified_after_save(document)
    return capture_save_invocation_gui(service, 
        document,
        path=preflight.path,
        expected_comparison_key=preflight.comparison_key,
        mode="save",
        previous_path=preflight.previous_path,
        validation_profile=preflight.validation_profile,
        destination_preexisted=True,
    )

def invoke_save_as_gui(
    service,
    document: Any,
    preflight: SavePreflight,
) -> SaveInvocation:
    """Revalidate preflight metadata and call ``saveAs`` on the GUI thread."""

    if not isinstance(preflight, SavePreflight) or preflight.mode != "save_as":
        raise InvalidSaveRequestError(
            "a Save As SavePreflight is required",
            stage="request_validation",
        )
    assert_document_path_gui(service, 
        document,
        expected_path=preflight.previous_path,
        expected_comparison_key=preflight.previous_comparison_key,
        require_clean=False,
        mutation_may_have_occurred=False,
    )
    if preflight.previous_path is not None:
        revalidate_file_metadata(service, 
            preflight.previous_path,
            preflight.source_baseline,
            role="save source",
            error_type=BaselineMismatchError,
        )
    revalidate_file_metadata(service, 
        preflight.path,
        preflight.destination_baseline,
        role="Save As destination",
        error_type=DestinationConflictError,
    )
    invoke_save_as(service, document, preflight.path)
    _clear_document_modified_after_save(document)
    return capture_save_invocation_gui(service, 
        document,
        path=preflight.path,
        expected_comparison_key=preflight.comparison_key,
        mode="save_as",
        previous_path=preflight.previous_path,
        validation_profile=preflight.validation_profile,
        destination_preexisted=preflight.destination_preexisted,
    )

def save_document(
    service,
    document: Any,
    *,
    expected_baseline: FileBaseline,
    expected_path: str | os.PathLike[str] | None = None,
    validation_profile: str = "default",
    domain_validator: DomainValidator | None = None,
) -> SaveResult:
    """Compare-before-save, call ``Document.save()``, and verify FCStd."""

    preflight = service.prepare_save(
        _document_filename(document),
        expected_baseline=expected_baseline,
        expected_path=expected_path,
        validation_profile=validation_profile,
    )
    invocation = service.invoke_save_gui(document, preflight)
    result = service.verify_saved_file(
        invocation,
        domain_validator=domain_validator,
    )
    service.revalidate_saved_document_gui(document, result)
    return result
