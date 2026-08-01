"""Typed save error-recovery GUI helpers."""

from ...save_service import SaveServiceError
from ._common import _rpc_mod, document_modified_or_dirty


def record_preflight_save_error(
    failure,
    *,
    phase,
    captured_identity,
    request_id,
    inflight,
):
    credential = phase["credential"]
    try:
        if (
            isinstance(failure, SaveServiceError)
            and failure.stage == "destination_preflight"
        ):
            _rpc_mod().document_lease_service.cancel_save_before_mutation(credential)
            return
        document = _rpc_mod().FreeCAD.getDocument(phase["document_name"])
        _rpc_mod().document_lease_service.record_error(
            credential,
            code=getattr(failure, "code", type(failure).__name__.upper()),
            message=_rpc_mod()._redact_rpc_diagnostic(
                failure,
                identity=captured_identity,
                inflight=inflight,
            ),
            request_id=request_id,
            dirty=(
                document_modified_or_dirty(document)
                if document is not None
                else True
            ),
        )
    except Exception:
        pass


def record_validation_save_error(
    failure,
    *,
    phase,
    captured_identity,
    request_id,
    inflight,
):
    try:
        credential = phase["credential"]
        document = _rpc_mod().FreeCAD.getDocument(phase["document_name"])
        _rpc_mod().document_lease_service.record_error(
            credential,
            code=getattr(failure, "code", type(failure).__name__.upper()),
            message=_rpc_mod()._redact_rpc_diagnostic(
                failure,
                identity=captured_identity,
                inflight=inflight,
            ),
            request_id=request_id,
            dirty=(
                document_modified_or_dirty(document)
                if document is not None
                else True
            ),
        )
    except Exception:
        pass
