# FreeCAD RPC Dispatcher and Isolated Worker Architecture

This document records the repository-specific architecture implemented in six ordered phases. The phases are autonomous validation checkpoints, not user approval gates.

For live-document ownership, authenticated mutation fencing, and verified save
finalization, see [Document leases](document-leases.md). Workers remain
snapshot-only: they may inspect or reopen-validate an immutable FCStd artifact,
but they never mutate or merge changes into a leased GUI document.

## 1. Verified repository findings

The original MCP path was `FreeCADConnection` → serialized `SimpleXMLRPCServer` → global request queue → 500 ms `QTimer` polling → GUI thread → global response queue. `addon/FreeCADMCP/rpc_server/rpc_server.py::FreeCADRPC.execute_code` ran arbitrary Python in the live GUI process, and `_get_res` used an uncorrelated global result queue. Several reads (`list_documents`, `get_recompute_log`, and `get_sketch_diagnostics`) accessed live FreeCAD state from the XML-RPC thread. `execution_safety.py::find_gui_blocking_risk` already rejected the known transformed-shape boolean audit.

The server derived from serialized `SimpleXMLRPCServer`, so a waiting worker call originally prevented `ping`, status, cancellation, and additional submissions. Docker provides lowercase `freecadcmd`. FreeCAD forwards script arguments following `--pass`. Real probes against Docker and the Windows development build showed that both `.py` and `.FCMacro` launch, but production retains only `worker_entry.py` to avoid two permanent execution paths. Numbered FCStd files reopen with altered document names, requiring exact-name aliases for dependency bundles.

## 2. Existing defects and risks

- Timer polling imposed up to 500 ms latency and unbounded draining could starve Qt events.
- Global responses lacked request correlation; late results could contaminate later calls.
- XML-RPC timeouts did not cancel already-started GUI work.
- OCC operations executing in the GUI thread are not safely interruptible.
- Live FreeCAD access from request threads violated GUI ownership.
- Serialized XML-RPC made status, cancellation, and queued jobs ineffective.
- AST inspection cannot fully understand dynamic arbitrary Python.
- `saveCopy()` can pause the GUI and does not make all GUI-side changes globally atomic.
- Worker process isolation is not a host security sandbox.

## 3. Assumptions

- Live document mutations execute only in the GUI process and are never merged from a worker snapshot.
- External dependencies must be open and resolvable; stale on-disk files are never substituted.
- Internal `Document.Name`, not editable `Label`, is identity.
- Snapshot reuse is deferred.
- Snapshot state fields are best-effort change indicators. They reduce mixed-state risk but cannot prove full atomicity against unrelated GUI-side changes.
- Worker failure never silently falls back to live GUI execution.

## 4. Final architectural decisions

`execution_safety.py::RequestClass` still describes the historical routing and is
used to diagnose unsafe mutating payloads. Under the document-lease design,
however, public arbitrary code with `read_only=true` always runs in a snapshot
FreeCADCmd worker—even when the caller requests `execution_mode="gui"` and even
when lease mode is off or observe. Information that genuinely requires the live
GUI is exposed through dedicated typed read methods. Workers never apply changes
to a leased live document; applying a worker-produced artifact is a separately
authenticated, leased GUI mutation.

`GuiDispatcher` owns per-request completion and correlation. It uses a queued Qt signal and executes one bounded request per callback. Queued and GUI-thread self-dispatch both call the same `_execute_request`, giving identical result and exception semantics without self-deadlock.

`FilteredXMLRPCServer` has a bounded five-thread executor, not unrestricted `ThreadingMixIn`. Three slots are reserved for general calls and two independent slots are reserved for control methods (`ping`, `get_worker_status`, `cancel_worker_job`, and `shutdown_rpc_server`). General saturation therefore cannot consume the control plane. `WorkerManager` admits exactly four worker calls: one active and at most three pending. It exposes active/pending IDs, supports targeted cancellation, and rejects saturation. This makes concurrent `ping`, status, cancellation, shutdown, and queued worker requests meaningful.

## 5. Rejected alternatives

- Global response queues: stale-result cross-contamination.
- Timer polling: latency and fragile wakeup behavior.
- Unrestricted request threads: resource exhaustion.
- Sending all reads to Qt: unknown expensive analysis can freeze the UI.
- Worker mutations or GUI fallback: changes would target snapshots or reintroduce hangs.
- Treating AST analysis as a security mechanism: dynamic Python defeats it.
- Opening numbered snapshots directly: breaks internal document-name identity.
- Loading saved external files: loses unsaved live state.
- Permanent `.py` plus `.FCMacro` launchers: duplicate runtime and test surface.
- Force-killing a live GUI operation: risks document corruption.

## 6. Exact files, classes, methods, and symbols affected

- `addon/FreeCADMCP/rpc_server/rpc_server.py`
  - `FilteredXMLRPCServer`, `FreeCADRPC.execute_code`, `_execute_code_worker`, `get_worker_status`, `cancel_worker_job`, `start_rpc_server`, and `stop_rpc_server`.
  - Removed `rpc_response_queue`, `_get_res`, and `process_gui_tasks`; all live reads use `_dispatch_gui`.
- `addon/FreeCADMCP/rpc_server/gui_dispatcher.py`
  - `GuiRequest`, `GuiOutcome`, `GuiDispatcher`, and the shared request executor.
- `addon/FreeCADMCP/rpc_server/execution_safety.py`
  - `RequestClass`, `classify_execute_code`, and retained `find_gui_blocking_risk`.
- `addon/FreeCADMCP/rpc_server/snapshot_service.py`
  - Snapshot coordination, dependency traversal, state checks, manifests, and exact-name aliases.
- `addon/FreeCADMCP/rpc_server/worker_protocol.py`
  - Schemas, validation, bounded stdout, JSON, code, artifact, and timeout limits.
- `addon/FreeCADMCP/rpc_server/worker_manager.py`
  - Executable discovery, bounded admission, lifecycle, status, cancellation, artifact promotion, and cleanup.
- `addon/FreeCADMCP/rpc_server/worker_entry.py`
  - The sole production FreeCADCmd entry point.
- `addon/FreeCADMCP/rpc_server/process_control.py`
  - Windows Job Object/process-tree and POSIX process-group termination.
- `src/freecad_mcp/execute_options.py`, `operations/core.py`, `operations/p5_measure.py`, `freecad_client.py`, and `server.py`
  - Worker/auto options, dedicated analysis routing, status, and cancellation API.
- `Dockerfile`
  - Supports `FreeCADCmd`, lowercase `freecadcmd`, and final FreeCAD fallback.
- Tests add dispatcher, classifier, worker protocol/process, queue, XML-RPC concurrency, snapshot, artifact, timeout, and recovery coverage.

## 7. Request and result flows

GUI request:

```text
bounded XML-RPC handler
→ GuiRequest
→ GuiDispatcher.submit
→ Qt queued signal
→ shared request executor on GUI thread
→ request-owned outcome/event
→ XML-RPC response
```

Worker request:

```text
bounded XML-RPC handler
→ validate options/limits
→ globally coordinated GUI snapshot
→ bounded worker admission
→ one active worker / three pending
→ FreeCADCmd worker_entry.py --pass job.json
→ validate result/artifacts
→ request-owned result and cleanup
```

## 8. Thread ownership and synchronization rules

`start_rpc_server()` requires a `QApplication`, runs on its thread, creates and retains `GuiDispatcher`, then starts XML-RPC. All live document and GUI state is read or changed through the dispatcher. Its queue and signal state share one lock; a signal is emitted only on an unscheduled-to-scheduled transition. Each Qt callback executes one request and schedules one continuation if needed. Timed-out, not-yet-started calls are cancellable, and late outcomes remain attached to their original requests.

Self-dispatch checks `QThread.currentThread() == dispatcher.thread()` and directly invokes the same `_execute_request` used by the queued callback. It never waits on its own completion event.

A global snapshot coordinator prevents concurrent snapshots. XML-RPC handlers and worker waits remain outside Qt. Worker state and admission have dedicated locks/semaphores and never use unrestricted thread creation.

## 9. Worker protocol and launcher

Phase 2 probed `.py` and `.FCMacro` in installed-style Docker and the Windows development build, including paths with spaces, exact argument forwarding, result creation, traceback, and exit behavior. Production selected one mechanism:

```text
FreeCADCmd worker_entry.py --pass job.json
```

Docker may use lowercase `freecadcmd`. The result path is stored inside `job.json`. Executable discovery order is: sibling command executable of the running GUI, `FreeCAD.getHomePath()/bin`, explicit configured path, environment override, then `PATH`. Candidates must exist, answer `--version` within five seconds, and successfully execute the protocol. Stable releases must match the full major/minor/patch version. Development builds must match that full version and the exact nonempty revision. A development/release pairing, patch mismatch, revision mismatch, or missing/ambiguous identity is rejected as `worker_version_mismatch`; a mismatched build is never silently accepted.

Jobs and results use schema version 1 and a UUID `job_id`. Jobs contain code, options, snapshot manifest, artifact staging directory, and result path. Results contain status, bounded stdout, session data, structured error/traceback, artifacts, and separate snapshot/worker metrics.

## 10. Snapshot and external-document behavior

Snapshot creation executes on Qt with no pre-snapshot recompute. It records active document; selection as document name, object name, and selected subelement names; filenames; labels; object counts; dependency set; dirty/change indicators; and duration before/after `saveCopy()`. A detected state/dependency change retries once, then returns `snapshot_state_changed`. These indicators are best effort and do not establish global atomicity.

Dependency traversal is cycle-safe and uses internal names. Every document is saved once to a numbered sanitized canonical filename and materialized as an exact-name hardlink alias, with quota-counted copy fallback. Dependencies open before the primary. The worker validates `App::Link`, `PropertyLink`/`PropertyXLink` variants, `LinkSub`, lists, target documents/objects, and one-based `FaceN`, `EdgeN`, and `VertexN` subelements after all documents are open. An invalid or non-surviving subelement produces the stable `external_subelement_unresolved` error; broken or unopened dependencies produce structured errors. Duplicate labels do not affect identity; unsafe names are rejected.

## 11. Timeout, resources, shutdown, and cleanup

Initial limits are: code 1 MiB, manifest 1 MiB, streaming stdout 1 MiB, result JSON 8 MiB, individual artifact 256 MiB, total artifacts 512 MiB/job, managed temporary root 2 GiB, default runtime 120 seconds, maximum 900 seconds, three pending workers, three general XML-RPC slots, and two reserved control slots. Stdout is capped while writing; excess output is discarded and marked truncated. The managed temporary root is scanned without following symlinks before admission, after staging, and every 100 ms while a worker runs. Exceeding the limit terminates the worker tree with `resource_limit_exceeded`. This is active bounded-interval enforcement, not a filesystem quota: growth between scans can temporarily overshoot the limit.

Windows workers use a new process group, no console window, and a kill-on-close Job Object, with bounded wait and `taskkill /T /F` fallback. POSIX workers use a new session, process-group `SIGTERM`, a two-second wait, then `SIGKILL`.

Shutdown order is: reject new requests/jobs, complete pending jobs with `server_stopping`, request active worker termination outside Qt, use bounded forced termination, initiate XML-RPC shutdown outside Qt, avoid unbounded GUI-thread joins, clean temporary resources outside Qt, and dispose Qt objects on Qt. An already-running live-document GUI operation cannot be safely interrupted; it is left draining.

Artifacts are staged privately, containment/size validated, promoted to manager ownership only after successful execution, assigned explicit handles/paths, expired after one hour, and removed on shutdown.

## 12. Security limitations

`FreeCADGui`, viewport state, selections, dialogs, and GUI modules are unsupported in workers. Detectable direct references/imports are rejected and headless failures use structured errors where possible. AST checks cannot stop dynamic imports. This is an API restriction, not a security sandbox: arbitrary Python retains the user account's filesystem, network, and process privileges. XML-RPC has no authentication or TLS; remote arbitrary execution is disabled by default.

## 13. Autonomous implementation phases

1. Per-request Qt dispatcher, removal of polling/global responses, GUI self-dispatch protection, and migration of live reads.
2. Explicit worker mode, one direct worker, primary snapshots, JSON protocol, timeout/tree kill, crash recovery, and one verified `.py` launcher.
3. Dependency bundles, cycles, exact-name aliases, unsaved dependencies, links/subelements, and state-change retry.
4. Structured BREP/STEP artifacts, quotas, ownership, expiry, and cleanup.
5. Snapshot-worker routing for every public arbitrary read-only payload, explicit
   typed GUI reads, and retained GUI safety checks for the separately enabled
   unsafe mutating-code compatibility path.
6. Five bounded XML-RPC handlers split into three general and two reserved control slots, one active/three pending workers, IDs, status, cancellation, admission control, and bounded shutdown.

An implementation agent executes all phases autonomously, runs tests after each phase, fixes regressions before continuing, does not weaken tests, does not silently skip a phase, and does not pause for routine confirmation. It stops only for a genuine repository blocker, unsafe operation, missing required external dependency, or contradiction not resolvable by inspection, and reports deviations with evidence.

## 14. Test and acceptance criteria

- Dispatcher: identical queued/self outcomes, no self-wait, no lost wakeup or stale result, one initial burst signal, and no direct request-thread FreeCAD access.
- Worker: one production launcher across Windows/development/Docker, spaced paths and lowercase command support, correct result/exit behavior, all resource limits, tree termination, crash recovery, and no GUI fallback.
- Snapshot: no pre-recompute, separate duration metrics, unchanged filenames/active/dirty/selection-subelement indicators, retry, serialization, cycles, duplicate labels, invalid names, broken links/subelements, stable invalid-subelement errors, and no stale disk substitution.
- Concurrency: `ping`/status/cancellation/shutdown through reserved control capacity while general handlers are saturated, targeted pending/active cancellation, bounded saturation, FIFO GUI dispatch, and safe bounded shutdown.
- Regression: all existing MCP unit/e2e tests and AutoCurtains document stability remain green; the original symmetry analysis executes in the worker or is hard-terminated without freezing Qt.

## 15. Remaining unavoidable limitations

- Mutating OCC work can still freeze Qt once started.
- `saveCopy()` can temporarily pause Qt and has no worker-style hard timeout.
- State indicators cannot prove fully atomic snapshots.
- AST cannot prove arbitrary code safe.
- Worker isolation does not secure the host account.
- Worker results represent snapshot time, not later edits.
- Broken or unopened dependencies cannot be reconstructed safely.
- Runtime temporary-root monitoring has a bounded scan interval and cannot prevent a transient overshoot between scans.

## 16. Open blockers

No source-architecture blocker remains. Production launcher evidence was obtained for Docker and the Windows development build, and `.py` was selected as the only retained path. Validation against any separately installed Windows FreeCAD distribution unavailable on the development host remains an environment coverage item rather than a reason to maintain a second launcher. In minimal Docker images, an orphaned descendant can remain as a non-running zombie when container PID 1 does not reap children; running the container with `--init` reaps it. The worker's invariant is that no descendant remains running, while strict zombie-reaping validation requires a real init/reaper and is tested with Docker `--init`.
