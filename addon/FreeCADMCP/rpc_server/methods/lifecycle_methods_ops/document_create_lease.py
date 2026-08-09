"""Leased document creation path for ``create_document``."""
from __future__ import annotations

import contextlib

import FreeCAD

try: from ....dispatch.request_cancellation_error import RequestCancellationError  # noqa: E701, I001 - frozen census lines
except ImportError: from dispatch.request_cancellation_error import RequestCancellationError  # noqa: E701, I001 - frozen census lines
from ...lease_runtime import _import_document_lease
from ...mutation_guard import RollbackCoverage


def validate_create_preflight(self, name, inflight):
    if inflight is not None:
        inflight.token.checkpoint("create_document_gui")
    try:
        existing_document = FreeCAD.getDocument(name)
    except NameError:
        existing_document = None
    if existing_document is not None:
        return {
            "success": False,
            "error_code": "DOCUMENT_ALREADY_OPEN",
            "error": f"Document {name!r} is already open",
        }
    if self._collaboration_collaborators.runtime_manifest is None:
        return {
            "success": False,
            "error_code": "LEASE_PROTOCOL_UNAVAILABLE",
            "error": "Authenticated runtime manifest is unavailable",
        }
    return None


def build_lease_owner(self, identity):
    collaborators = self._collaboration_collaborators
    lifecycle = self._lifecycle_collaborators
    manifest = collaborators.runtime_manifest
    lease = _import_document_lease()
    return lease.LeaseOwner(
        addon_profile_id=manifest.profile_id,
        addon_runtime_id=manifest.addon_runtime_id,
        freecad_pid=manifest.freecad_pid,
        freecad_process_started_at=manifest.freecad_process_started_at,
        boot_id=manifest.boot_id,
        mcp_instance_id=identity.get("instance_id") or "",
        mcp_pid=int(identity.get("pid") or 0),
        mcp_process_started_at=identity.get("mcp_process_started_at")
        or collaborators.addon_loaded_at,
        hostname=lifecycle.document_lease_service.local_runtime_identity.hostname,
        mcp_hostname=identity.get("host") or "",
        client=identity.get("client") or "",
        agent_id=identity.get("agent_id") or "",
    )


def complete_create_grant(self, *, name, document, grant, inflight):
    try:
        from document_lease import core_authority

        core_authority.sync_owner_from_lease_record(document, grant.record)
    except Exception:
        FreeCAD.Console.PrintWarning(
            "[MCP] core mutation owner sync failed after create\n"
        )
    response = {
        "success": True,
        "document_name": name,
        **grant.to_dict(),
        "expiry_policy": {
            "heartbeat_interval_seconds": 10,
            "sidecar_flush_interval_seconds": 30,
            "stale_after_seconds": 90,
        },
    }
    response.update(
        self._observed_document_evidence(
            "create_document",
            document,
            coverage=RollbackCoverage.PARTIAL,
        )
    )
    return response


def abort_failed_create(
    self, name, identity, reservation, selector, snapshot_id, exc
):
    lifecycle = self._lifecycle_collaborators
    service = lifecycle.document_lease_service
    if reservation is not None:
        with contextlib.suppress(Exception):
            service.abort_acquisition(reservation.credential)
    retained = None
    if selector is not None:
        try:
            retained = service.get(selector)
        except Exception:
            retained = None
    if retained is None:
        if snapshot_id:
            self._collaboration_collaborators.discard_lease_baseline_snapshot(
                snapshot_id
            )
        with contextlib.suppress(Exception):
            FreeCAD.closeDocument(name)
    return lifecycle.lease_service_error(
        exc, request_id=identity.get("request_id")
    )


def create_and_lease(self, name, identity, inflight):
    preflight_error = validate_create_preflight(self, name, inflight)
    if preflight_error is not None:
        return preflight_error
    lifecycle = self._lifecycle_collaborators
    collaboration = self._collaboration_collaborators
    service = lifecycle.document_lease_service
    dl = lifecycle.import_document_lock()
    if inflight is not None:
        inflight.token.begin_mutation("create_document_invocation")
    created = self._create_document_gui(name)
    if created is not True:
        return {"success": False, "error": str(created)}
    document = FreeCAD.getDocument(name)
    snapshot_id = ""
    selector = None
    reservation = None
    marker_keys = []
    attribution_started = False
    try:
        if document is None:
            raise RuntimeError("FreeCAD did not publish the new document")
        document_identity = lifecycle.ensure_v2_document(document)
        selector = {
            "document_session_uuid": document_identity.session_uuid,
            "document_name": document_identity.name,
        }
        marker_keys = [document_identity.name, document_identity.session_uuid]
        dl.begin_agent_mutation_scope(identity.get("request_id"), marker_keys)
        attribution_started = True
        owner = build_lease_owner(self, identity)
        live_request_ids = (
            collaboration.inflight_request_registry.active_lifecycle_request_ids()
            if collaboration.inflight_request_registry is not None
            else frozenset()
        )
        reservation = service.begin_acquisition(
            selector,
            owner,
            task_summary="Create new document",
            document_dirty=False,
            acquisition_request_id=identity.get("request_id"),
            live_acquisition_request_ids=live_request_ids,
        )
        self._retain_inflight_credential(reservation.credential)
        if inflight is not None:
            inflight.token.checkpoint("create_document_snapshot_invocation")
        snapshot_id = collaboration.create_lease_baseline_snapshot_gui(document)
        if inflight is not None:
            inflight.token.checkpoint("create_document_snapshot_complete")
        grant = service.complete_acquisition(
            reservation.credential,
            baseline=None,
            baseline_validated=False,
            snapshot_id=snapshot_id,
        )
        return complete_create_grant(
            self,
            name=name,
            document=document,
            grant=grant,
            inflight=inflight,
        )
    except RequestCancellationError:
        self._complete_request_cancellation(inflight, dirty=True, snapshot_id=snapshot_id)
        raise
    except Exception as exc:
        return abort_failed_create(
            self, name, identity, reservation, selector, snapshot_id, exc
        )
    finally:
        if attribution_started:
            dl.end_agent_mutation_scope(identity.get("request_id"), marker_keys)
