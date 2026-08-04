"""LOCKED_ERROR handoff grant during acquisition snapshot."""

def grant_locked_error_handoff(
    self,
    *,
    phase,
    task_description,
    observed,
    document,
    document_dirty,
    original_identity,
):
    collaborators = self._collaboration_collaborators
    lease = collaborators.import_document_lease()
    grant = collaborators.document_lease_service.claim_locked_error_handoff(
        phase["exact_selector"],
        phase["owner"],
        validation=lease.LiveDocumentValidation(
            document=observed,
            document_modified=document_dirty,
            baseline=phase["baseline"],
            baseline_validated=bool(original_identity.canonical_path),
        ),
        local_confirmation=bool(phase.get("locked_error_handoff_authorized")),
        task_summary=task_description,
    )
    credential = grant.credential
    phase["credential"] = credential
    self._retain_inflight_credential(credential)
    try:
        from document_lease import core_authority

        core_authority.sync_owner_from_lease_record(document, grant.record)
    except Exception:
        collaborators.freecad.Console.PrintWarning(
            "[MCP] core mutation owner sync failed after LOCKED_ERROR handoff\n"
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
