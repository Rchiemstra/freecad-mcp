"""Lease RPC methods extracted from ``FreeCADRPC`` (Phase 4 slice 4E)."""

from contextlib import suppress


def save_document(self, selector, validation_profile="default"):
    collaborators = self._lifecycle_collaborators
    identity = collaborators.import_document_lock().get_request_identity()
    if identity.get("lease_token") and not identity.get("lease_credentials"):
        return self._run_legacy_save(
            selector,
            validation_profile=validation_profile,
        )
    return self._run_typed_save(
        selector,
        mode="save",
        validation_profile=validation_profile,
    )


def save_document_as(
    self,
    selector,
    destination,
    overwrite=False,
    expected_destination_sha256="",
    validation_profile="default",
):
    return self._run_typed_save(
        selector,
        mode="save_as",
        destination=destination,
        overwrite=overwrite,
        expected_destination_sha256=expected_destination_sha256,
        validation_profile=validation_profile,
    )


def finalize_document_edit(
    self,
    selector,
    save_mode="save",
    destination="",
    overwrite=False,
    expected_destination_sha256="",
    validation_profile="default",
):
    collaborators = self._lifecycle_collaborators
    normalized = str(save_mode).lower().replace("-", "_")
    if normalized not in {"save", "save_as", "saveas", "first_save"}:
        return {
            "success": False,
            "error_code": "INVALID_SAVE_MODE",
            "error": "save_mode must be save, save_as, or first_save",
        }
    identity = collaborators.import_document_lock().get_request_identity()
    if identity.get("lease_token") and not identity.get("lease_credentials"):
        if normalized != "save":
            return {
                "success": False,
                "error_code": "LEASE_PROTOCOL_REQUIRED",
                "error": (
                    "Protocol-v1 compatibility supports same-path finalization "
                    "only; Save As and first save require protocol v2"
                ),
            }
        saved = self._run_legacy_save(
            selector,
            validation_profile=validation_profile,
        )
        if not saved.get("success"):
            return saved
        lease_payload = saved.get("lease") or {}
        doc_key = str(lease_payload.get("doc_key") or "")
        token = str(identity.get("lease_token") or "")
        released = collaborators.import_document_lock().release_lease(doc_key, token)
        if not released.get("success"):
            return {
                **saved,
                "success": False,
                "error_code": released.get("error_code", "LEASE_RELEASE_FAILED"),
                "error": released.get(
                    "error", "Verified save completed but release failed"
                ),
                "release": released,
                "released": False,
            }
        saved["release"] = released
        saved["released"] = True
        with suppress(Exception):
            collaborators.refresh_lock_indicator()
        return saved
    return self._run_typed_save(
        selector,
        mode=(
            "save_as"
            if normalized in {"save_as", "saveas", "first_save"}
            else "save"
        ),
        destination=destination,
        overwrite=overwrite,
        expected_destination_sha256=expected_destination_sha256,
        validation_profile=validation_profile,
        release=True,
    )
