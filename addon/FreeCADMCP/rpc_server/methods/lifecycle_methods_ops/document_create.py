from __future__ import annotations

import FreeCAD

from ...mutation_guard import RollbackCoverage


def create_document(self, name="New_Document"):
    self._request_checkpoint("create_document_start")

    def create_with_evidence():
        result = self._create_document_gui(name)
        if result is True:
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
            "error": result,
            **self._unknown_mutation_evidence(
                "create_document",
                declared_documents=(name,),
                coverage=RollbackCoverage.PARTIAL,
                reason="document creation failed before postflight validation",
            ),
        }

    response = self._dispatch_gui(create_with_evidence)
    if isinstance(response, dict):
        return response
    return {
        "success": False,
        "error": response,
        **self._unknown_mutation_evidence(
            "create_document",
            declared_documents=(name,),
            coverage=RollbackCoverage.PARTIAL,
            reason="GUI dispatch failed before document creation completed",
        ),
    }
