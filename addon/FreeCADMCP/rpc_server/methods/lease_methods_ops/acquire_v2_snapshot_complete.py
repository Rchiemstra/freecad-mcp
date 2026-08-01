"""Normal acquisition completion after snapshot."""

from ._common import _rpc_mod


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
    _rpc_mod().document_lease_service.record_acquisition_snapshot(
        credential,
        snapshot_id=snapshot_id,
    )
    completion = (
        _rpc_mod().document_lease_service.complete_dirty_adoption
        if adopt_dirty
        else _rpc_mod().document_lease_service.complete_acquisition
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
        _rpc_mod().FreeCAD.Console.PrintWarning(
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
