import os

try:
    from document_state import require_document_modified
except ImportError:
    from addon.FreeCADMCP.document_state import require_document_modified

from ._common import RpcHelperDependencies

"""Live validation and mutation file metadata helpers."""

def _live_validation_evidence(
    document,
    document_identity,
    record,
    dependencies: RpcHelperDependencies,
):
    """Build release evidence without hashing the document on Qt.

    Clean release is allowed only for a record whose verified baseline is at
    least as new as its final mutation.  The immediate GUI-thread check uses
    that baseline's stat metadata plus the live document/file identity; the
    full SHA and worker validation were already completed at save promotion.
    """

    lease = dependencies.import_document_lease()
    live = dependencies.document_identity_service.inspect_registered_document(
        document_identity.session_uuid, document
    )
    _assert_mutation_file_metadata_unchanged(record, dependencies)
    baseline_current = bool(
        record.baseline is not None
        and record.validation_complete
        and record.last_verified_save_revision >= record.last_mutation_revision
    )
    return lease.LiveDocumentValidation(
        document=live,
        document_modified=require_document_modified(document),
        baseline=record.baseline,
        baseline_validated=baseline_current,
    )


def _assert_mutation_file_metadata_unchanged(
    record, dependencies: RpcHelperDependencies
):
    """Reject an externally changed saved file before a GUI mutation starts.

    Full SHA-256 verification remains outside the GUI thread at acquisition and
    save boundaries.  This immediate GUI-thread check compares the stable file
    identity (already re-resolved by the injected credential collaborator), size, and
    nanosecond mtime so queued work cannot proceed after an ordinary external
    replacement or edit.
    """

    lease = dependencies.import_document_lease()
    path = record.document.canonical_path
    if not path:
        return
    baseline = record.baseline
    if baseline is None:
        raise lease.LiveDocumentValidationError(
            "saved lease has no verified file baseline"
        )
    try:
        current = os.stat(path)
    except OSError as exc:
        raise lease.LiveDocumentValidationError(
            f"leased document file is unavailable: {exc}"
        ) from exc
    if int(current.st_size) != baseline.size:
        raise lease.LiveDocumentValidationError(
            "leased document file size changed externally"
        )
    if int(current.st_mtime_ns) != baseline.mtime_ns:
        raise lease.LiveDocumentValidationError(
            "leased document modification time changed externally"
        )
