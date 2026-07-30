# Lease recovery

Recovery is deliberately conservative: a missing heartbeat is evidence of
uncertainty, not permission to delete a lock. Keep the FCStd, adjacent sidecar,
guard, and profile `lease-recovery` snapshots together until the document has
been inspected and resolved.

## Status actions

| Status | Agent writes | Recommended action |
|---|---|---|
| `LOCKED_ERROR` | Fenced, but resumable | The credential owner may correct or retry through health-checked typed tools. A different MCP process may continue a dirty document in the same FreeCAD runtime only after local confirmation atomically rotates the credential. After that FreeCAD runtime exits, a clean reopen may self-recover only when the saved FCStd still exactly matches the original baseline |
| `STALE` | Blocked | If the exact authenticated runtime returns unchanged, reconcile; otherwise inspect and confirm local takeover |
| `USER_INTERVENED` | Old credential permanently revoked | Finish locally with save-and-clear, restore-and-clear, or keep-dirty acknowledgement |
| `UNLOCKED_DIRTY` | Blocked until current state is verified | After restart, a clean acquire or explicitly confirmed dirty adoption may self-recover only with exact document/file validation and proof that the recorded FreeCAD owner is dead |
| Missing/replaced sidecar | Blocked by default | A clean acquire may self-recover only from an imported `LOCKED_IDLE` record with an unchanged validated baseline and proven-inactive authority; otherwise use confirmed recovery |
| Malformed/unknown sidecar | Blocked | Preserve or quarantine through the local recovery UI after owner/liveness checks; never edit it in place |

## Common failures

- **MCP crash or lost network:** after 90 seconds the lease becomes stale. An
  exact token/runtime/generation may reconcile if neither document nor sidecar
  changed; otherwise take over locally.
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
  that the recorded FreeCAD owner is dead. Promoted leases still require
  explicit recovery.
- **Close and reopen in the same FreeCAD process:** an unlocked document drops
  its old proxy registration. A document with local or foreign recovery
  authority retains a one-shot marker and may rebind only the same name, path,
  and filesystem identity. Untouched reservations can then retry; promoted
  leases remain blocked for explicit recovery.
- **Sidecar deleted after foreign import:** a normal clean acquire performs one
  bounded in-process recovery only when the immutable record is `LOCKED_IDLE`,
  clean, non-migrating, fully save-verified, and its foreign runtime or document
  session is provably inactive. The live document must be clean and an off-GUI
  SHA-256 baseline must exactly match the persisted baseline. The addon then
  atomically creates a higher-generation `ACQUIRING` sidecar; a changed,
  malformed, or concurrently recreated sidecar still fails closed. This path
  also repairs exact-proxy identity drift under the same evidence, avoiding a
  stacked `DOCUMENT_IDENTITY_ERROR`.
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
  continue, `adopt_dirty_document` presents local confirmation, verifies that
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
  Acquisition/create credentials are one-time results; if their response was
  lost, the replay status is `ACQUISITION_RESULT_NOT_REPLAYABLE` and local
  recovery is required rather than issuing a second acquisition.
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
