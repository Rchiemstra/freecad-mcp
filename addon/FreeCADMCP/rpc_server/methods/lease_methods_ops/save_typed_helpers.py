"""Shared helpers for typed save lifecycle."""

import os

from ...mutation_guard import RollbackCoverage
from ...save_service import SaveServiceError


def make_error_response(self, exc, *, mode, request_id, phase, collaborators):
    if isinstance(exc, SaveServiceError):
        response = {
            "success": False,
            "error_code": exc.code,
            "error": str(exc),
            "save_error": exc.to_dict(request_id=request_id),
        }
    else:
        response = collaborators.lease_service_error(exc, request_id=request_id)
    response.update(
        self._unknown_mutation_evidence(
            f"{mode}_document",
            declared_documents=(
                (phase["document_name"],) if phase.get("document_name") else ()
            ),
            coverage=RollbackCoverage.PARTIAL,
            reason=f"save lifecycle failed: {type(exc).__name__}",
        )
    )
    return response


def marker_keys_for(document, document_identity, destination):
    candidates = {
        str(getattr(document, "Name", "") or ""),
        str(document_identity.name or ""),
        str(document_identity.session_uuid or ""),
        str(getattr(document, "FileName", "") or ""),
        str(document_identity.canonical_path or ""),
        str(destination or ""),
    }
    for candidate in tuple(candidates):
        if not candidate:
            continue
        candidates.add(os.path.normcase(candidate))
        if os.path.isabs(candidate):
            candidates.add(os.path.normcase(os.path.realpath(candidate)))
    return sorted(candidates - {""})
