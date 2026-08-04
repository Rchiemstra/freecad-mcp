"""Normal acquisition completion after snapshot."""

def complete_normal_acquisition(
    self,
    *,
    phase,
    adopt_dirty,
    credential,
    snapshot_id,
    document,
    original_identity,
):
    collaborators = self._collaboration_collaborators
    collaborators.document_lease_service.record_acquisition_snapshot(
        credential,
        snapshot_id=snapshot_id,
    )
    completion = (
        collaborators.document_lease_service.complete_dirty_adoption
        if adopt_dirty
        else collaborators.document_lease_service.complete_acquisition
    )
    grant = completion(
        credential,
        baseline=phase["baseline"],
        baseline_validated=bool(original_identity.canonical_path),
        snapshot_id=snapshot_id,
    )
    try:
        from document_lease import core_authority

        core_authority.sync_owner_from_lease_record(document, grant.record)
    except Exception:
        collaborators.freecad.Console.PrintWarning(
            "[MCP] core mutation owner sync failed after acquire\n"
        )
    return {
        "success": True,
        **grant.to_dict(),
        "expiry_policy": {
            "heartbeat_interval_seconds": 10,
            "sidecar_flush_interval_seconds": 30,
            "stale_after_seconds": 90,
        },
    }
