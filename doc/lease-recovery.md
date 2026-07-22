# Lease recovery

Recovery is deliberately conservative: a missing heartbeat is evidence of
uncertainty, not permission to delete a lock. Keep the FCStd, adjacent sidecar,
guard, and profile `lease-recovery` snapshots together until the document has
been inspected and resolved.

## Status actions

| Status | Agent writes | Recommended action |
|---|---|---|
| `LOCKED_ERROR` | Blocked except typed retry/restore paths | Read the structured error, fix the cause, retry save/validation, or restore the baseline |
| `STALE` | Blocked | If the exact authenticated runtime returns unchanged, reconcile; otherwise inspect and confirm local takeover |
| `USER_INTERVENED` | Old credential permanently revoked | Finish locally with save-and-clear, restore-and-clear, or keep-dirty acknowledgement |
| `UNLOCKED_DIRTY` | Blocked and no new acquisition | Inspect, save or restore locally, then clear/adopt explicitly |
| Missing/replaced sidecar | Blocked | Repair it under the guard only when exact ownership can be proven; otherwise use confirmed recovery |
| Malformed/unknown sidecar | Blocked | Preserve or quarantine through the local recovery UI after owner/liveness checks; never edit it in place |

## Common failures

- **MCP crash or lost network:** after 90 seconds the lease becomes stale. An
  exact token/runtime/generation may reconcile if neither document nor sidecar
  changed; otherwise take over locally.
- **FreeCAD crash or reboot:** reopen the file, inspect the foreign recovery
  record, verify the last saved FCStd and snapshot, then choose save, restore,
  or dirty acknowledgement.
- **GUI timeout/hang:** treat the running mutation as uncertain until the GUI
  returns. Do not retry with a new request ID or clear its sidecar blindly.
  Retrying the same request ID returns the recorded status and never invokes
  the mutation again. An uncertainty tombstone remains for the addon-process
  lifetime even if lease authority itself cannot be found.
- **Cancellation:** queued work may return to idle only if it never began.
  Cancellation during a mutation ends in error until save or restore proves the
  document state.
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
├─ secure baseline is available → restore, inspect, then save and verify
└─ state must remain dirty → confirmed takeover and keep-dirty acknowledgement

USER_INTERVENED
├─ keep the local edits → save, reopen-verify, and clear
├─ discard local edits → restore baseline, then save/verify and clear
└─ defer resolution → acknowledge UNLOCKED_DIRTY (new agents remain blocked)

UNLOCKED_DIRTY
├─ save or restore can be verified → clear the recovery record
└─ not yet safe → leave the record and sidecar in place
```
