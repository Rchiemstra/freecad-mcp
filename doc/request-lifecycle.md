# Timeout, cancellation, recovery, and MCP Tasks

GUI dispatch uses typed codes rather than parsing messages:

- `GUI_TIMEOUT_BEFORE_EXECUTION`: removed from the queue; no GUI execution began.
- `GUI_TIMEOUT_DURING_EXECUTION`: the callable continues and completion is uncertain.
- `GUI_BUSY_AFTER_TIMEOUT`: new GUI work is quarantined behind uncertain work.
- `GUI_TASK_FAILED` / `GUI_DISPATCH_FAILED`: typed execution/dispatch failures.

Worker lifecycle uses `WORKER_TIMEOUT_DURING_EXECUTION`,
`WORKER_CANCEL_REQUESTED`, `WORKER_CANCELLED`,
`WORKER_TERMINATION_FAILED`, and `WORKER_TASK_FAILED`. Responses retain
`legacy_error_code` where an older lowercase lifecycle code changed.

After a timeout, call `get_request_status(request_id)`. States are `queued`,
`running`, `running_after_timeout`, `completed`, `failed`, `cancel_requested`,
`cancelled`, `completed_after_cancel_request`, `unknown`, or `expired`.
The response includes stage, execution/mutation start, cancellation,
uncertainty, late-result availability, and `recovery_incident_id`.

For acquire/adopt/create, status may also report `result_claimable` and a
redacted `acquisition_claim` block. Raw lease tokens are never included.
Reclaim a lost success with `claim_acquisition_result` (general serialized
sync-tool lane) or by replaying the original authenticated request ID while the
private claim vault holds the credential. The MCP control lane is
`cancel_request` and `get_request_status` only; custody via
`claim_acquisition_result` is isolated from cancel on the sync-tool lane (D6). An unacknowledged claim is not TTL-pruned or
capacity-evicted, and the configured capacity is soft: a new raw credential is
retained rather than rejected after authority may have published. Claims peek
until `acknowledge_acquisition_claim` (or first authorized use) scrubs the
vault. The MCP client auto-polls
status/claim after an acquire/adopt/create transport timeout and surfaces
`request_id` when recovery remains pending.

Document acquisition deadline hierarchy:

- Authorization (dirty adoption): all agent-start dirty adoption is
  auto-authorized with no FreeCAD pop-up. Taking over another agent's dirty
  ``LOCKED_ERROR`` lease returns a non-error `LOCKED_ERROR_HANDOFF_PENDING`
  immediately with a `request_id`; bounded GUI revalidation and hash/CAS claim
  then escrow the credential. Resume with `get_request_status` (control lane)
  then the public `claim_acquisition_result` (general serialized sync-tool lane)
  to custody the lease into this process without exposing the raw token. Claim-phase GUI timeouts
  leave the continuation `claiming_uncertain` until a late CAS escrows the
  grant; they do not journal a terminal failure over a possible late success.
- Each acquire GUI phase (`reserve`, `snapshot/promote`): `ACQUIRE_GUI_PHASE_TIMEOUT_S` (45s).
- Off-GUI baseline hash: `ACQUIRE_HASH_TIMEOUT_S` (30s); on exceed, abort `ACQUIRING`.
- Client lifecycle socket: `CLIENT_LIFECYCLE_TIMEOUT_S` (150s; `FreeCADConnection` default).
- Required ordering: `2 × 45 + 30 + cleanup/response headroom <= 150`.
- Heartbeat-expiry recovery (90s) remains a last-resort fallback. Positive
  dead-MCP proof for an eligible clean lease may trigger guarded owner-exit
  recovery sooner.
- Same-MCP fencing of an unreturned `ACQUIRING` requires the recorded
  `acquisition_request_id` to be absent from live acquire/adopt/create inflight IDs.

`cancel_request` is cooperative. Before mutation it cancels queued work; after
mutation begins it fences the affected lease and reports
`REQUEST_CANCELLED_AFTER_MUTATION`. For async ``LOCKED_ERROR`` handoff,
`cancel_request` also cancels the detached handoff continuation only
before the atomic ``begin_claim`` gate (`state=cancelled`,
`handoff_pending=false`); later queued handoff work does not rotate ownership. After
``begin_claim`` or vault escrow, cancel returns ``REQUEST_NOT_CANCELLABLE`` and
the credential remains claimable.
Same-runtime and cached-foreign orphan recovery likewise accept cancellation
through snapshot and revalidation, then atomically close cancellation before
sidecar/core handoff. Cached-foreign dirty state must enter through
`adopt_dirty_document`; recovery never clears its live `Modified` state. The
new credential enters the private claim vault before in-memory publication; a
core or vault failure rolls back prior authority (or CAS-deletes the exact
newly created sidecar), while a post-boundary GUI timeout leaves the successful
credential claimable. If sidecar publication is reported uncertain after
`os.replace` or atomic no-replace `os.link`, an exact guarded read proves the
intended record when available. If the read itself is unavailable, the
known-published record still receives matching core authority and an escrowed
credential, and the result carries `SIDECAR_COMMIT_UNCERTAIN`. A readable
mismatch or incomplete/uncertain core/sidecar rollback retains the recovery
snapshot.
A timeout-during-execution creates a recovery incident. Late completion emits
`recovery_completed` (or `recovery_failed`) and stays correlated to the original
request.

Heavy tools accept the SDK's negotiated task-augmented calls. MCP task IDs are
linked to existing request and worker IDs; status/result/list/cancel use the
SDK task store. Clients without task capability receive the unchanged
synchronous response. The extension is enabled defensively and falls back
synchronously on SDKs that do not provide it.

Timeout during GUI execution:

```json
{"status":"timed_out","error_code":"GUI_TIMEOUT_DURING_EXECUTION","execution":{"stage":"during_execution"},"data":{"mutation_started":true,"completion_uncertain":true,"recovery_incident_id":"..."}}
```
