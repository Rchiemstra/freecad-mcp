from __future__ import annotations

from dataclasses import dataclass

from .document_identity import DocumentIdentity
from .file_baseline import FileBaseline


@dataclass(frozen=True)
class LiveDocumentValidation:
    """Fresh addon-owned evidence used for stale recovery and clean release.

    ``document`` must be captured from the currently open FreeCAD document,
    while ``baseline`` describes the file observed immediately before the
    protected operation.  The explicit validation flag prevents an old record
    from being mistaken for new evidence when a caller skipped hashing or
    domain validation.
    """

    document: DocumentIdentity
    document_modified: bool
    baseline: FileBaseline | None
    baseline_validated: bool

LiveDocumentValidation.__module__ = "document_lease.model"
