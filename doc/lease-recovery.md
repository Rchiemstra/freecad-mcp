# Lease recovery

Recovery is deliberately conservative: a missing heartbeat is evidence of
uncertainty, not permission to delete a lock. Keep the FCStd, adjacent sidecar,
guard, and profile `lease-recovery` snapshots together until the document has
been inspected and resolved.

## Status actions

| Status | Agent writes | Recommended action |
|---|---|---|
| `LOCKED_IDLE` | Exclusive while the owner is live | A replacement MCP in the same live addon/FreeCAD runtime may recover only when the recorded MCP is positively co-located and proven dead, and the clean live document plus saved FCStd exactly match the fully verified baseline |
| `LOCKED_ERROR` | Fenced, but resumable | The credential owner may correct or retry through health-checked typed tools. A different MCP process may automatically continue a dirty document in the same FreeCAD runtime after live revalidation atomically rotates the credential; no agent-start pop-up is shown. After that FreeCAD runtime exits, a clean reopen may self-recover only when the saved FCStd still exactly matches the original baseline |
| `STALE` | Blocked | If the exact authenticated runtime returns unchanged, reconcile. An eligible clean local lease with co-located dead-MCP proof may use the guarded acquisition handoff; otherwise inspect and confirm local takeover |
| `USER_INTERVENED` | Old credential permanently revoked | A replacement MCP may self-recover only when all prior mutations were save-verified and fresh live/file validation is exact. A clean document uses acquire; a dirty document uses confirmed adoption and remains dirty. Local records require dead-MCP proof or the narrow pre-fix worker-snapshot signature; imported records independently require inactive foreign-FreeCAD proof. Intentional takeover with a live or unknown owner remains blocked |
| `UNLOCKED_DIRTY` | Blocked until current state is verified | After restart, a clean acquire or explicitly confirmed dirty adoption may self-recover only with exact document/file validation and proof that the recorded FreeCAD owner is dead |
| Missing/replaced sidecar | Blocked by default | A clean acquire may self-recover from a fully verified imported `LOCKED_IDLE` record. The exact legacy worker-snapshot `USER_INTERVENED` record may also self-recover: clean through acquire or dirty through confirmed adoption. Both require an unchanged baseline and proven-inactive foreign authority; arbitrary missing authority remains blocked |
| Malformed/unknown sidecar | Blocked | Preserve or quarantine through the local recovery UI after owner/liveness checks; never edit it in place |

## Common failures

- **MCP crash while FreeCAD/addon remains live:** a fully save-verified clean
  `LOCKED_IDLE` lease can become `LEASE_OWNER_EXITED` as soon as exact
  co-location and process identity prove the MCP exited, without waiting for
  heartbeat expiry. An eligible `LOCKED_IDLE`, `STALE`, or fully save-verified
  `USER_INTERVENED` record may then be acquired by a replacement MCP only after
  a core-authorized recovery snapshot, fresh clean GUI validation, exact
  saved-file hash/identity verification, sidecar CAS rotation to a higher
  generation, and exact core-fence read-back. A core mismatch returns no new
  credential and CAS-republishes the prior authority at newer record/state
  revisions; that rollback is permitted only because the prior credential was
  already proven inactive or irrevocably revoked. After successful rotation,
  the old credential remains fenced. If `os.replace` publishes the new sidecar
  but a later permission or directory-sync check fails, recovery proceeds only
  when a guarded strict read matches every intended persisted field. If the
  strict read itself is unavailable, the known-published successor still
  completes core handoff and credential escrow and returns
  `SIDECAR_COMMIT_UNCERTAIN`; this avoids stopping with a new sidecar whose raw
  token was discarded. A readable mismatch fails closed and preserves the
  recovery snapshot.
- **Pre-fix worker snapshot reported as user intervention:** the exact
  `freecad_mcp_workers/.../snapshots/NNNN_*.FCStd` save signature may use the
  same guarded acquisition path after exact validation. A clean live document
  uses `acquire_document_lock`; a dirty one uses `adopt_dirty_document`, takes
  a fresh recovery snapshot, and remains dirty. For a process-local record,
  takeover already rotated to a discarded credential, so legacy records
  without an MCP hostname remain safe to recover. An imported cached record
  must additionally prove its recorded foreign FreeCAD runtime inactive;
  diagnostic text alone is never authority. Other intentional intervention
  remains blocked.
- **Lost network or unproven MCP liveness:** after 90 seconds the lease becomes
  stale. An exact token/runtime/generation may reconcile if neither document
  nor sidecar changed; otherwise take over locally. Timeout or uncertain
  liveness alone never authorizes automatic rotation.
- **FreeCAD crash or reboot:** reopen the file, inspect the foreign recovery
  record, verify the last saved FCStd and snapshot, then choose save, restore,
  or dirty acknowledgement.
- **GUI Ctrl+S during an unreturned acquisition:** the observer fences the
  reservation and refreshes an atomic same-path FCStd replacement against the
  exact live document proxy. Because supported GUI builds clear
  `Gui::Document.Modified` after the finish-save observer callback returns, a
  queued second pass records the resulting clean state without ever taking
  over an attributed agent save. A clean retry may CAS-replace only that
  untouched reservation. After a restart, the same retry also requires proof
  that the recorded FreeCAD owner is dead. Other promoted leases still require
  explicit recovery unless they satisfy the guarded same-runtime dead-MCP
  handoff.
- **Close and reopen in the same FreeCAD process:** an unlocked document drops
  its old proxy registration. A document with local or foreign recovery
  authority retains a one-shot marker and may rebind only the same name, path,
  and filesystem identity. Untouched reservations can then retry; promoted
  leases remain blocked unless they satisfy a guarded recovery path.
- **Sidecar deleted after foreign import:** a normal clean acquire performs one
  bounded in-process recovery when the immutable record is either fully
  verified clean `LOCKED_IDLE` authority or the exact verified legacy
  worker-snapshot `USER_INTERVENED` shape. The latter does not require
  `validation_complete=true`, but it must retain a baseline, have
  `last_verified_save_revision == last_mutation_revision`, and have no active
  migration. The addon repairs only exact-proxy identity metadata, hashes the
  saved FCStd off the GUI thread, proves the foreign FreeCAD authority
  inactive, and snapshots the live document. Dirty state is never relabelled:
  it requires `adopt_dirty_document` and remains dirty. After revalidation, one
  irreversible transaction atomically creates completed higher-generation
  authority, verifies the core owner/generation/provider, escrows the raw
  credential, and only then replaces the cached foreign record in memory. A
  core or escrow failure CAS-deletes only that exact new sidecar, restores the
  prior core state, and retains the cached record. A changed, malformed, or
  concurrently recreated sidecar still fails closed. Post-publication create
  uncertainty is handled like replacement uncertainty: the exact successor
  continues to core handoff and escrow with `SIDECAR_COMMIT_UNCERTAIN`, while
  a mismatch retains the recovery snapshot.
- **Saved `UNLOCKED_DIRTY` sidecar after restart:** a normal clean acquire or
  explicitly confirmed dirty adoption may import the unchanged terminal
  recovery record even when the user's atomic save replaced the FCStd
  filesystem identity. This covers files that reopen dirty because FreeCAD
  migrated a deprecated property. The addon proves the recorded FreeCAD owner
  dead, validates the exact live document lifecycle, hashes and revalidates the
  current saved file, then CAS-replaces the unchanged sidecar with a
  higher-generation `ACQUIRING` record. It never deletes the sidecar or creates
  an unlocked gap. A live/unknown owner, unconfirmed dirty document, malformed
  record, changed path, concurrent sidecar update, or file change during
  validation remains blocked.
- **Typed operation failure:** the transaction rolls back but the visible
  `LOCKED_ERROR` fence remains. The credential owner may retry or correct the
  failure with typed, scoped mutation tools; arbitrary `execute_code` and
  legacy nested-code helpers remain blocked. If another MCP process must
  continue, `adopt_dirty_document` verifies that
  the saved baseline is unchanged, preserves the recovery snapshot, and
  atomically rotates the lease ID, generation, token digest, and owner.
- **Dirty `LOCKED_ERROR` after closing without saving:** a normal acquire may
  import and fence the foreign recovery record when the reopened document is
  clean, the recorded FreeCAD process is proven dead, and a fresh SHA-256
  baseline exactly matches the errored lease's original saved-file baseline.
  The old MCP client process does not keep authority alive after its bound
  FreeCAD runtime has exited. A changed file, live/unknown FreeCAD owner,
  missing recovery snapshot, or concurrent sidecar update remains blocked.
- **GUI timeout/hang:** treat the running mutation as uncertain until the GUI
  returns. Do not retry with a new request ID or clear its sidecar blindly.
  Retrying the same request ID returns the recorded status and never invokes
  the mutation again. An uncertainty tombstone remains for the addon-process
  lifetime even if lease authority itself cannot be found.
- **Cancellation:** queued work may return to idle only if it never began.
  Cancellation during a mutation ends in error until save or restore proves the
  document state.
- **Crash after acquisition `saveCopy`:** the snapshot ID is checkpointed in
  the `ACQUIRING` sidecar before promotion. Recovery retains that snapshot and
  refuses automatic reservation replacement, because it may contain unsaved
  user work.
- **Save failure/disk full:** retain ownership and sidecars, free space or pick a
  safe Save As destination, then retry. A failed save is never a clean release.
- **Save As conflict:** the original document remains owned and the destination
  is untouched when conflict is detected before `saveAs`.
- **Crash during Save As:** inspect both source and destination sidecars. A
  shared `migration_id` and complementary `source`/`destination` roles identify
  one handoff; each object also names both canonical paths and comparison keys.
  Destination-first publication and source removal after promotion ensure at
  least one fence survives every interruption.
- **External file replacement/move:** mutation and save stop. Reconcile the
  filesystem identity or select a verified new destination.
- **System sleep/debugger pause:** a long gap may appear stale. The exact owner
  can revalidate; no timeout alone clears ownership.
- **Lost response/session refresh:** retry only with the original request ID and
  unchanged method, parameters, operation metadata, and lease credentials. A
  renewed session token is expected and does not change request identity.
  Acquisition/create credentials are one-time results and are never stored in
  the public replay cache. After a transport-lost success, the same
  authenticated MCP runtime may reclaim the credential repeatedly through
  `claim_acquisition_result` or by replaying the original request ID until it
  acknowledges custody (`acknowledge_acquisition_claim`) or first uses the
  credential. Unacknowledged vault entries do not expire, get evicted for a
  newer claim, or get rejected at the configured soft capacity. Preserving the
  only raw token takes precedence over that process-local memory target.
  `get_request_status` may report `result_claimable` / redacted
  claim metadata, never the raw token. The MCP client automatically polls
  status/claim after an acquire/adopt transport timeout and surfaces
  `request_id` when recovery remains pending.
- **Interrupted dirty adoption before promotion:** all agent-start dirty
  adoption is auto-authorized with no FreeCAD pop-up. A live ``LOCKED_ERROR``
  handoff returns `LOCKED_ERROR_HANDOFF_PENDING` immediately while a background
  continuation performs bounded GUI authorization/revalidation and hash/CAS
  claim. It escrows the credential for control-lane polling via
  `get_request_status` then the public
  `claim_acquisition_result` tool (custodies locally; never returns the raw
  token). Cancel the pre-CAS continuation with `cancel_request` only before the
  atomic `begin_claim` gate; after that boundary cancel is not-cancellable and
  the credential stays claimable when escrowed. Post-gate CAS/validation failure
  still becomes terminal `failed` (no credential). A claim-phase GUI timeout
  leaves the handoff uncertain until late CAS completion rather than journaling
  a terminal failure over a possible grant. Bounded reserve/hash/promote phases
  use
  `ACQUIRE_GUI_PHASE_TIMEOUT_S` (45s) and `ACQUIRE_HASH_TIMEOUT_S` (30s) so
  `2 × 45 + 30 + cleanup <= CLIENT_LIFECYCLE_TIMEOUT_S` (150s) for non-dialog
  work. A timeout or cancel after `ACQUIRING` publication aborts the
  mutation-free reservation or lets the same MCP instance fence it only when
  that acquisition request ID is no longer live; the 90-second stale watchdog
  remains only a last-resort fallback.
- **`REPLAY_JOURNAL_FULL`:** no protected entry was evicted. Resolve/finalize
  outstanding leases or restart FreeCAD only through the normal recovery path;
  never work around the error by changing request IDs repeatedly.

## Takeover checklist

1. Confirm the selected document, previous owner, heartbeat age, dirty state,
   last operation, and whether a baseline snapshot exists.
2. Check whether the previous MCP and FreeCAD runtimes still exist. Do not use
   PID alone; process-start, boot, runtime, and profile identity matter.
3. Use the dock's selected-document Take Over action. This increments the
   generation and revokes the old credential.
4. Inspect/recompute the model before editing further.
5. Finish with a verified save, baseline restore, or explicit keep-dirty
   acknowledgement. Only the first two can produce a clean release.

Never delete `.freecad-mcp.lock` or its `.guard` merely because it is old. If
the UI cannot prove recovery safely, preserve the files and copy the FCStd
before performing manual diagnosis.

See [lease client scenarios](lease-client-scenarios.md) for the save/reconnect
sequence diagrams and tested refusal matrix.

## Save As recovery pairs

A restarted addon may show two immutable foreign records for one interrupted
Save As. Correlate them only when the migration UUID, lease ID, generation,
owner, and endpoint identities agree, then inspect both FCStd files and the
recovery snapshot. A destination-only record can still name its source when a
crash occurred before the source linkage CAS. A source-only record can name
the intended destination when promotion or source removal did not complete.

Do not infer completion from one missing peer and do not delete either record
because its heartbeat is stale. Resolution remains a confirmed local recovery
action; there is no automatic pair cleanup. Public recovery details expose the
linkage paths, roles, and migration ID, never tokens or fingerprints.

## Troubleshooting decision tree

```text
STALE
├─ exact runtime + token + generation + document + baseline still match
│  └─ authenticated reconcile, then continue or finalize
└─ anything differs or ownership cannot be proven
   └─ confirmed local takeover → USER_INTERVENED

LOCKED_ERROR
├─ save/validation failure is retryable → retry typed save or validation
├─ synthetic FOREIGN_SIDECAR_INVALID over a clean verified foreign record
│  └─ clean acquire → hash/identity/liveness proof → atomic generation fence
├─ synthetic FOREIGN_SIDECAR_INVALID over verified legacy worker intervention
│  ├─ live document clean → acquire → snapshot + atomic fenced handoff
│  └─ live document dirty → adopt dirty → snapshot + atomic fenced handoff
├─ old FreeCAD exited + clean reopen + original saved baseline unchanged
│  └─ clean acquire → dead-FreeCAD proof + exact hash → atomic generation fence
├─ secure baseline is available → restore, inspect, then save and verify
└─ state must remain dirty → confirmed takeover and keep-dirty acknowledgement

USER_INTERVENED
├─ keep the local edits → save, reopen-verify, and clear
├─ discard local edits → restore baseline, then save/verify and clear
└─ defer resolution → acknowledge UNLOCKED_DIRTY (new agents remain blocked)

UNLOCKED_DIRTY
├─ current recovery runtime can save or restore → verify and clear
├─ restarted runtime + clean exact document + dead owner
│  └─ clean acquire → hash/identity/liveness proof → atomic generation fence
├─ restarted runtime + confirmed dirty adoption + dead owner
│  └─ snapshot + hash/identity/liveness proof → atomic generation fence
└─ not yet safe → leave the record and sidecar in place
```
