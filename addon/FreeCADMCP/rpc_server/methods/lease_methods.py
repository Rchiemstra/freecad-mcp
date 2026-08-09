"""Frozen compatibility RPCs for the removed MCP document authority.

Native FreeCAD collaboration owns document authority after the collaboration
cutover.  These callables intentionally retain the legacy parameter surface so
older clients receive one deterministic deprecation result instead of an
unknown-method transport error.
"""

from typing import Any


def _legacy_lease_authority_removed() -> dict[str, Any]:
    """Return a fresh result for a removed legacy authority operation."""

    return {
        "success": False,
        "ok": False,
        "error_code": "LEGACY_LEASE_AUTHORITY_REMOVED",
        "error": "Document authority is owned by native FreeCAD collaboration.",
    }


def acknowledge_acquisition_claim(self, request_id):
    return _legacy_lease_authority_removed()


def acquire_document_lock(
    self,
    doc_name: str = "",
    file_path: str = "",
    session_id: str = "",
    task_description: str = "",
    client: str = "",
    selector: dict[str, Any] | None = None,
    agent_id: str = "",
    hash_policy: str = "sha256",
) -> dict[str, Any]:
    return _legacy_lease_authority_removed()


def acquire_document_lock_v2(
    self,
    requested_selector,
    *,
    request_identity,
    task_description,
    client,
    agent_id,
    hash_policy,
    adopt_dirty=False,
):
    return _legacy_lease_authority_removed()


def adopt_dirty_document(
    self,
    selector: dict[str, Any] | None = None,
    task_description: str = "",
    client: str = "",
    agent_id: str = "",
    hash_policy: str = "sha256",
) -> dict[str, Any]:
    return _legacy_lease_authority_removed()


def claim_acquisition_result(self, request_id):
    return _legacy_lease_authority_removed()


def escrow_locked_error_handoff_claim(
    self,
    *,
    mcp_runtime_id,
    request_id,
    claimed,
):
    return _legacy_lease_authority_removed()


def finalize_document_edit(
    self,
    selector,
    save_mode="save",
    destination="",
    overwrite=False,
    expected_destination_sha256="",
    validation_profile="default",
):
    return _legacy_lease_authority_removed()


def force_release_stale_lock(self, doc_key: str) -> dict[str, Any]:
    return _legacy_lease_authority_removed()


def get_document_lock(
    self,
    doc_name: str = "",
    file_path: str = "",
    session_id: str = "",
    selector: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _legacy_lease_authority_removed()


def heartbeat_document_lock(
    self,
    doc_key: str,
    token: str,
    current_operation: str = "",
    state: str = "",
    document_dirty: bool | None = None,
) -> dict[str, Any]:
    return _legacy_lease_authority_removed()


def journal_handoff_terminal(self, *, mcp_runtime_id, request_id, response):
    return _legacy_lease_authority_removed()


def lease_heartbeat_batch(self, leases, client_monotonic_ns=""):
    return _legacy_lease_authority_removed()


def lease_reconcile(self, credential):
    return _legacy_lease_authority_removed()


def list_document_locks(self) -> dict[str, Any]:
    return _legacy_lease_authority_removed()


def release_document_lock(
    self,
    doc_key: str = "",
    token: str = "",
    selector: dict[str, Any] | None = None,
    disposition: str = "saved",
) -> dict[str, Any]:
    return _legacy_lease_authority_removed()


def run_legacy_save(self, selector, *, validation_profile="default"):
    return _legacy_lease_authority_removed()


def run_locked_error_handoff_continuation(
    self,
    *,
    request_id,
    mcp_runtime_id,
    requested_selector,
    task_description,
    phase,
):
    return _legacy_lease_authority_removed()


def run_typed_save(
    self,
    selector,
    *,
    mode,
    destination="",
    overwrite=False,
    expected_destination_sha256="",
    validation_profile="default",
    release=False,
):
    return _legacy_lease_authority_removed()


def save_document(self, selector, validation_profile="default"):
    return _legacy_lease_authority_removed()


def save_document_as(
    self,
    selector,
    destination,
    overwrite=False,
    expected_destination_sha256="",
    validation_profile="default",
):
    return _legacy_lease_authority_removed()


def start_locked_error_handoff_continuation(
    self,
    *,
    request_id,
    mcp_runtime_id,
    requested_selector,
    task_description,
    phase,
):
    return _legacy_lease_authority_removed()


def update_document_lock(
    self,
    selector,
    task_description="",
    progress_detail="",
):
    return _legacy_lease_authority_removed()


__all__ = [
    "acknowledge_acquisition_claim",
    "acquire_document_lock",
    "acquire_document_lock_v2",
    "adopt_dirty_document",
    "claim_acquisition_result",
    "escrow_locked_error_handoff_claim",
    "finalize_document_edit",
    "force_release_stale_lock",
    "get_document_lock",
    "heartbeat_document_lock",
    "journal_handoff_terminal",
    "lease_heartbeat_batch",
    "lease_reconcile",
    "list_document_locks",
    "release_document_lock",
    "run_legacy_save",
    "run_locked_error_handoff_continuation",
    "run_typed_save",
    "save_document",
    "save_document_as",
    "start_locked_error_handoff_continuation",
    "update_document_lock",
]
