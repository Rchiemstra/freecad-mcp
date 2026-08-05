from __future__ import annotations

import FreeCAD

from ...mutation_guard import RollbackCoverage
from .document_create_lease import create_and_lease


def create_document(self, name="New_Document"):
    lifecycle = self._lifecycle_collaborators
    dl = lifecycle.import_document_lock()
    identity = dl.get_request_identity()
    inflight = self._current_inflight()
    self._request_checkpoint("create_document_start")

    if lifecycle.document_lease_service is not None and identity.get(
        "authenticated_session_id"
    ):
        response = self._dispatch_gui(
            lambda: create_and_lease(self, name, identity, inflight)
        )
        if isinstance(response, dict) and "document_health" not in response:
            response = {
                **response,
                **self._unknown_mutation_evidence(
                    "create_document",
                    declared_documents=(name,),
                    coverage=RollbackCoverage.PARTIAL,
                    reason=("document creation did not reach validated postflight"),
                ),
            }
        return response

    res = self._dispatch_gui(lambda: self._create_document_gui(name))
    if res is True:
        document = FreeCAD.getDocument(name)
        response = {"success": True, "document_name": name}
        if document is not None:
            response.update(
                self._observed_document_evidence(
                    "create_document",
                    document,
                    coverage=RollbackCoverage.PARTIAL,
                )
            )
        else:
            response.update(
                self._unknown_mutation_evidence(
                    "create_document",
                    declared_documents=(name,),
                    coverage=RollbackCoverage.PARTIAL,
                    reason="new document was not available for validation",
                )
            )
        return response
    return {
        "success": False,
        "error": res,
        **self._unknown_mutation_evidence(
            "create_document",
            declared_documents=(name,),
            coverage=RollbackCoverage.PARTIAL,
            reason="document creation failed before postflight validation",
        ),
    }
