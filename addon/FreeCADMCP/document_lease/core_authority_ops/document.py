"""FreeCAD document resolution and mutation-authority API probes."""

from __future__ import annotations

from typing import Any


def resolve_document(document_or_name: Any) -> Any | None:
    if document_or_name is None:
        return None
    if (
        (
            hasattr(document_or_name, "openMutationCapability")
            or hasattr(document_or_name, "Name")
        )
        and (
            callable(getattr(document_or_name, "openMutationCapability", None))
            or hasattr(document_or_name, "Objects")
        )
    ):
        # Prefer objects that look like FreeCAD documents.
        return document_or_name
    try:
        import FreeCAD  # type: ignore

        return FreeCAD.getDocument(str(document_or_name))
    except Exception:
        return None


def core_authority_available(document: Any | None = None) -> bool:
    """Return True when FreeCAD exposes the mutation-authority Python API."""

    if document is not None:
        return callable(getattr(document, "openMutationCapability", None))
    try:
        import FreeCAD  # type: ignore

        doc_type = getattr(FreeCAD, "Document", None)
        if doc_type is not None and callable(
            getattr(doc_type, "openMutationCapability", None)
        ):
            return True
        active = getattr(FreeCAD, "ActiveDocument", None)
        if active is not None:
            return callable(getattr(active, "openMutationCapability", None))
    except Exception:
        return False
    return False


def core_owner_api_available(document: Any) -> bool:
    """Return True when any core owner/fence API is exposed on a document.

    A partial API is treated as present so verified handoffs fail closed rather
    than silently falling back to observer-only compatibility.
    """

    doc = resolve_document(document)
    if doc is None:
        return False
    return any(
        callable(getattr(doc, name, None))
        for name in (
            "setMutationOwner",
            "mutationAuthorityStatus",
            "openMutationCapability",
        )
    )
