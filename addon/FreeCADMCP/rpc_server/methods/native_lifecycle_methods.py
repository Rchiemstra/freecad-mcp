"""Native FreeCAD save lifecycle RPC methods.

These methods resolve a live document and delegate persistence to FreeCAD.  They
do not compare FCStd baselines, create authority sidecars, hold credentials, or
decide recovery/lease state.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any


def _error(code: str, message: str) -> dict[str, Any]:
    return {"success": False, "error_code": code, "error": message}


def _selector_error(selector: Any) -> dict[str, Any] | None:
    if not isinstance(selector, Mapping):
        return _error("DOCUMENT_NOT_FOUND", "selector did not resolve a live document")
    if str(selector.get("document_session_uuid") or ""):
        return _error(
            "DOCUMENT_SESSION_SELECTOR_DEPRECATED",
            "legacy document_session_uuid selectors do not identify native FreeCAD documents",
        )
    return None


def _resolve_document_gui(facade: Any, selector: Mapping[str, Any]):
    if not isinstance(selector, Mapping):
        return None
    freecad = facade._execution_collaborators.freecad
    documents = tuple(freecad.listDocuments().values())
    resolved: list[Any] = []

    name = str(selector.get("document_name") or "")
    if name:
        document = freecad.getDocument(name)
        if document is None:
            return None
        resolved.append(document)

    requested_path = str(selector.get("canonical_path") or "")
    if requested_path:
        expected = os.path.normcase(os.path.realpath(requested_path))
        matching = []
        for document in documents:
            current = str(getattr(document, "FileName", "") or "")
            if current and os.path.normcase(os.path.realpath(current)) == expected:
                matching.append(document)
        if len(matching) != 1:
            return None
        resolved.append(matching[0])

    if not resolved or any(document is not resolved[0] for document in resolved[1:]):
        return None
    return resolved[0]


def _save_gui(document: Any) -> dict[str, Any]:
    if not str(getattr(document, "FileName", "") or ""):
        return _error("DOCUMENT_HAS_NO_FILE", "Save As is required for this document")
    saved = document.save()
    if saved is False:
        return _error("NATIVE_SAVE_REJECTED", "FreeCAD rejected the save")
    return {
        "success": True,
        "saved": True,
        "document_name": str(getattr(document, "Name", "") or ""),
        "canonical_path": str(getattr(document, "FileName", "") or ""),
        "authority": "native_freecad",
    }


def _save_as_gui(document: Any, destination: str, overwrite: bool) -> dict[str, Any]:
    if not destination:
        return _error("DESTINATION_REQUIRED", "destination is required")
    save_with_policy = getattr(document, "saveAsWithPolicy", None)
    if not callable(save_with_policy):
        return _error(
            "NATIVE_SAVE_AS_POLICY_UNAVAILABLE",
            "FreeCAD does not expose the required native Save As policy boundary",
        )
    outcome = save_with_policy(str(destination), bool(overwrite))
    if not isinstance(outcome, Mapping):
        return _error("NATIVE_SAVE_AS_REJECTED", "FreeCAD returned an invalid Save As result")
    if outcome.get("status") == "destination_exists":
        return _error("DESTINATION_EXISTS", "Save As destination already exists")
    if outcome.get("success") is not True:
        return _error("NATIVE_SAVE_AS_REJECTED", "FreeCAD rejected Save As")
    return {
        "success": True,
        "saved": True,
        "document_name": str(getattr(document, "Name", "") or ""),
        "canonical_path": str(getattr(document, "FileName", "") or destination),
        "authority": "native_freecad",
    }


def _resolve_and_save_gui(facade: Any, selector: Mapping[str, Any]) -> dict[str, Any]:
    document = _resolve_document_gui(facade, selector)
    if document is None:
        return _error("DOCUMENT_NOT_FOUND", "selector did not resolve a live document")
    return _save_gui(document)


def _resolve_and_save_as_gui(
    facade: Any,
    selector: Mapping[str, Any],
    destination: str,
    overwrite: bool,
) -> dict[str, Any]:
    document = _resolve_document_gui(facade, selector)
    if document is None:
        return _error("DOCUMENT_NOT_FOUND", "selector did not resolve a live document")
    return _save_as_gui(document, destination, overwrite)


def save_document(self, selector, validation_profile="default"):
    if validation_profile != "default":
        return _error(
            "VALIDATION_PROFILE_UNSUPPORTED",
            "Native FreeCAD persistence does not accept MCP validation profiles",
        )
    selector_failure = _selector_error(selector)
    if selector_failure is not None:
        return selector_failure
    result = self._dispatch_gui(lambda: _resolve_and_save_gui(self, selector))
    return result if isinstance(result, dict) else _error("NATIVE_SAVE_FAILED", str(result))


def save_document_as(
    self,
    selector,
    destination,
    overwrite=False,
    expected_destination_sha256="",
    validation_profile="default",
):
    if validation_profile != "default":
        return _error(
            "VALIDATION_PROFILE_UNSUPPORTED",
            "Native FreeCAD persistence does not accept MCP validation profiles",
        )
    if expected_destination_sha256:
        return _error(
            "EXPECTED_DESTINATION_HASH_UNSUPPORTED",
            "Native FreeCAD persistence does not use MCP FCStd hash authority",
        )
    selector_failure = _selector_error(selector)
    if selector_failure is not None:
        return selector_failure
    result = self._dispatch_gui(
        lambda: _resolve_and_save_as_gui(self, selector, destination, overwrite)
    )
    return result if isinstance(result, dict) else _error("NATIVE_SAVE_FAILED", str(result))


def finalize_document_edit(
    self,
    selector,
    save_mode="save",
    destination="",
    overwrite=False,
    expected_destination_sha256="",
    validation_profile="default",
):
    if save_mode == "save":
        result = save_document(self, selector, validation_profile)
    elif save_mode in {"save_as", "first_save"}:
        result = save_document_as(
            self,
            selector,
            destination,
            overwrite,
            expected_destination_sha256,
            validation_profile,
        )
    else:
        return _error("INVALID_SAVE_MODE", f"Unsupported save_mode: {save_mode}")
    if not result.get("success"):
        return result
    return {
        **result,
        "finalized": True,
        "released": True,
        "release": {"authority": "native_freecad", "lease_present": False},
    }


__all__ = ["finalize_document_edit", "save_document", "save_document_as"]
