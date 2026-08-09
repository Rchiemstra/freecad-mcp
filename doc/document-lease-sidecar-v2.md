# Document lease sidecar schema v2

A saved `Part.FCStd` is coordinated through:

```text
Part.FCStd.freecad-mcp.lock
Part.FCStd.freecad-mcp.lock.guard
```

The sidecar is a cross-process fence. The live addon registry, authenticated
RPC session, document identity, generation, token, and sidecar must all agree;
the sidecar alone never grants permission to mutate.

## Wire shape

The strict schema is produced by `LeaseRecord.to_sidecar_dict()`:

```json
{
  "schema_version": 2,
  "record_kind": "freecad-mcp-document-lease",
  "record_revision": 18,
  "lease_id": "uuid",
  "generation": 7,
  "token_fingerprint": "sha256:<64 lowercase hex characters>",
  "migration": {
    "migration_id": "uuid",
    "source": {
      "canonical_path": "/models/Part.FCStd",
      "comparison_key": "/models/Part.FCStd"
    },
    "destination": {
      "canonical_path": "/models/Part-v2.FCStd",
      "comparison_key": "/models/Part-v2.FCStd"
    },
    "role": "source"
  },
  "document": {
    "session_uuid": "uuid",
    "name": "Part",
    "canonical_path": "/models/Part.FCStd",
    "comparison_key": "/models/Part.FCStd",
    "file_identity": {"platform": "posix", "device": 1, "inode": 2}
  },
  "owner": {
    "addon_profile_id": "profile-id",
    "addon_runtime_id": "uuid",
    "freecad_pid": 1234,
    "freecad_process_started_at": "RFC3339Z",
    "boot_id": "boot-id",
    "mcp_instance_id": "uuid",
    "mcp_pid": 5678,
    "mcp_process_started_at": "RFC3339Z",
    "hostname": "host",
    "client": "freecad-mcp",
    "agent_id": "agent"
  },
  "lease": {
    "state": "LOCKED_EDITING",
    "state_revision": 12,
    "acquired_at": "RFC3339Z",
    "last_heartbeat_at": "RFC3339Z",
    "heartbeat_sequence": 43,
    "current_operation": "Create Pad",
    "task_summary": ""
  },
  "document_state": {
    "dirty": true,
    "user_intervened": false,
    "last_mutation_revision": 9,
    "last_successful_save_at": null,
    "last_verified_save_revision": 8,
    "baseline": {"mtime_ns": 0, "size": 0, "sha256": "...", "file_identity": null},
    "error": null,
    "validation_complete": false,
    "snapshot_id": "uuid"
  }
}
```

`migration` is normally null. During Save As, both sidecars carry the same
random `migration_id` and path identities; the source uses role `source` and
the destination uses role `destination`. The parser rejects unknown fields,
invalid UUIDs or roles, partial path pairs, equal source/destination comparison
keys, and a role whose path does not match that sidecar's `document` identity.
For first save only, the source path pair may be null because no source
sidecar exists. Older schema-v2 records that omit `migration` remain readable.

The raw lease token is never serialized. Public status also omits its
fingerprint. PIDs and wall-clock values are useful only together with runtime,
process-start, boot, and authenticated-session identities.

Migration paths and ID may appear in redacted local or foreign-recovery
status so two records can be correlated after a restart. Neither the migration
object nor public status contains a raw token or token fingerprint.

## Save As ordering

1. Atomically create the destination `ACQUIRING` sidecar with the destination
   role. It fully names both endpoints even if the process stops immediately.
2. CAS-update the source sidecar with the matching source role. `saveAs` is not
   called until the destination reservation exists.
3. After save and verification, CAS-promote the destination record.
4. CAS-remove the source sidecar only after the destination is authoritative.
5. CAS-clear `migration` from the destination. Clean success is reported only
   after this final metadata update succeeds.

A failure before source removal leaves the source and/or destination record in
place. A failure while clearing the final destination linkage retains or
synthesizes a conservative `LOCKED_ERROR`; it does not report a clean Save As.
Recovery never deletes either correlated record automatically.

Document paths, host/client labels, operation names, and task summaries are
diagnostic metadata and may be sensitive. Full bounded task metadata remains
in the process-local registry and may appear in authenticated public status,
but the persisted `task_summary` is empty by default. Setting
`persist_task_summary_in_sidecar=true` is an explicit privacy opt-in: the addon
then removes control/format characters, collapses whitespace to one line, and
persists at most 256 characters. Even with the opt-in, do not place prompts,
credentials, customer data, or proprietary details in task metadata.

## Filesystem behavior

- JSON is limited to 64 KiB and validated for exact structure, types, UUIDs,
  timestamps, state invariants, and bounded strings.
- The persistent guard uses `flock` on POSIX and `LockFileEx` on Windows.
- Updates read and compare lease ID, generation, fingerprint, and revision
  while holding the guard, write a complete temporary file, flush it, and
  atomically replace the sidecar. Clean release is compare-and-remove.
- Sidecar, guard, and temporary files are owner-only. Symlinks and non-regular
  sidecars are rejected.
- UNC/network paths are rejected by default because lock and rename semantics
  vary. `allow_network_sidecar` is an explicit lower-assurance override.
- Missing, malformed, oversized, replaced, permission-denied, or unknown
  sidecars fail closed. They are not auto-deleted.

Schema-v1 records are treated as legacy locked/unknown. Recovery must prove
ownership or receive local confirmation before quarantining one. Downgrading
must not remove an active v2 or dirty-recovery record.
