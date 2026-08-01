"""Thin SaveService façade binding extracted save helpers."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from typing import Any

from ..save_types.archive_verification import ArchiveVerification

try:
    from document_lease.identity import capture_file_baseline
    from document_lease.model import FileBaseline
except ImportError:
    from addon.FreeCADMCP.document_lease.identity import capture_file_baseline
    from addon.FreeCADMCP.document_lease.model import FileBaseline

from .archive import verify_fcstd_archive
from .service_finalize import finalize_document_edit as _finalize_document_edit
from .service_finalize import save_document_as as _save_document_as
from .service_invoke import invoke_save_as_gui as _invoke_save_as_gui
from .service_invoke import invoke_save_gui as _invoke_save_gui
from .service_invoke import save_document as _save_document
from .service_preflight import canonical_path as _canonical_path
from .service_preflight import preflight_destination as _preflight_destination
from .service_preflight import preflight_source_path as _preflight_source_path
from .service_preflight import prepare_save as _prepare_save
from .service_preflight import prepare_save_as as _prepare_save_as
from .service_revalidate import assert_document_path_gui as _assert_document_path_gui
from .service_revalidate import capture_save_invocation_gui as _capture_save_invocation_gui
from .service_revalidate import invoke_save as _invoke_save
from .service_revalidate import invoke_save_as as _invoke_save_as
from .service_revalidate import revalidate_file_metadata as _revalidate_file_metadata
from .service_verify import revalidate_saved_document_gui as _revalidate_saved_document_gui
from .service_verify import verify_saved_file as _verify_saved_file

DomainValidator = Callable[[str, str], Mapping[str, Any] | bool | None]
DestinationGuardFactory = Callable[[str], AbstractContextManager[Any]]


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

    prepare_save = _prepare_save
    prepare_save_as = _prepare_save_as
    verify_saved_file = _verify_saved_file
    revalidate_saved_document_gui = _revalidate_saved_document_gui
    invoke_save_gui = _invoke_save_gui
    invoke_save_as_gui = _invoke_save_as_gui
    save_document = _save_document
    save_document_as = _save_document_as
    finalize_document_edit = _finalize_document_edit

    _canonical = _canonical_path
    _preflight_source_path = _preflight_source_path
    _preflight_destination = _preflight_destination
    _revalidate_file_metadata = _revalidate_file_metadata
    _assert_document_path_gui = _assert_document_path_gui
    _invoke_save = _invoke_save
    _invoke_save_as = _invoke_save_as
    _capture_save_invocation_gui = _capture_save_invocation_gui
