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

`cancel_request` is cooperative. Before mutation it cancels queued work; after
mutation begins it fences the affected lease and reports
`REQUEST_CANCELLED_AFTER_MUTATION`. A timeout-during-execution creates a
recovery incident. Late completion emits `recovery_completed` (or
`recovery_failed`) and stays correlated to the original request.

Heavy tools accept the SDK's negotiated task-augmented calls. MCP task IDs are
linked to existing request and worker IDs; status/result/list/cancel use the
SDK task store. Clients without task capability receive the unchanged
synchronous response. The extension is enabled defensively and falls back
synchronously on SDKs that do not provide it.

Timeout during GUI execution:

```json
{"status":"timed_out","error_code":"GUI_TIMEOUT_DURING_EXECUTION","execution":{"stage":"during_execution"},"data":{"mutation_started":true,"completion_uncertain":true,"recovery_incident_id":"..."}}
```
