# GUI-thread geometry-loop guard, recovery, and future container worker

This document records the 2026-07-22 GUI-thread freeze, the routing guard that now
prevents it, the operational recovery runbook, and a deferred design for a containerized
worker. It complements the
[worker architecture plan](freecad_rpc_worker_architecture_plan.md); workers remain
snapshot-only and never mutate a leased GUI document.

## 1. Incident and root cause

An `execute_code` request ran a 45-iteration loop that changed a `Placement.Rotation`,
recomputed the document, and called `Shape.common()` + `distToShape()` per iteration. It
was submitted with `execution_mode="gui"` and `read_only` omitted (`false`). Python/OCCT
code already running on FreeCAD's Qt GUI thread is **not interruptible**: neither the
client's request cancel nor the add-on's 120 s dispatcher timeout could stop it, so FreeCAD
became unresponsive and rejected further GUI work (`GUI_BUSY_AFTER_TIMEOUT`). The isolated
`FreeCADCmd.exe` worker was `available: idle` throughout but was never selected.

Root cause: the static detector `execution_safety.py::find_gui_geometry_loop_risk`
correctly flagged the loop, but the gate in `rpc_server.py::execute_code` only blocked
`execution_mode="auto"` mutations and `execution_mode="gui"` code falsely marked
`read_only`. An explicit `gui + read_only=false` "mutation" was exempt by design — exactly
the path this request took.

## 2. The guard (current behavior)

`rpc_server.py::execute_code` now adds a third block condition:

```python
allow_gui_loop        = bool(options.get("allow_gui_geometry_loop", False))
block_forced_gui_loop = execution_mode == "gui" and not read_only and not allow_gui_loop
```

Routing for code that `find_gui_geometry_loop_risk` flags:

| execution_mode | read_only | allow_gui_geometry_loop | result |
|----------------|-----------|-------------------------|--------|
| `worker`       | `true`    | –                       | isolated FreeCADCmd worker |
| `auto`         | `true`    | –                       | isolated FreeCADCmd worker |
| `gui`          | `true`    | –                       | worker (read-only never runs on GUI) |
| `auto`         | `false`   | –                       | **blocked** (unmarked mutation) |
| `gui`          | `false`   | `false`                 | **blocked** (the 2026-07-22 case) |
| `gui`          | `false`   | `true`                  | runs on GUI (explicit opt-in) |

`read_only=true` still permits temporarily rotating/recomputing geometry inside the worker
snapshot; it only forbids modifying the live GUI documents. Use it for all analysis. The
`allow_gui_geometry_loop=true` override is reserved for a genuine, bounded live-document
mutation that cannot run against a snapshot, and should be split into small chunks.

The rule is surfaced to agents in the `execute_code` tool docstring
(`src/freecad_mcp/server.py`) and the `asset_creation_strategy` MCP prompt.

## 3. Recovery runbook (GUI is unresponsive)

If FreeCAD is already frozen by an in-flight GUI request:

1. **Do not submit more GUI work.** New GUI requests are rejected with
   `GUI_BUSY_AFTER_TIMEOUT` and add nothing but noise until the stuck call finishes.
2. **Poll, don't push.** Call `get_worker_status` (an out-of-process RPC) and a lightweight
   GUI liveness ping. Wait for the in-flight request to actually complete — a non-interruptible
   OCCT call can run for minutes after the RPC has already returned `completion_uncertain`.
3. **Only if truly hung:** identify the `FreeCAD.exe` PID listening on the RPC port
   (default `9875`) and terminate it, then relaunch. Killing mid-mutation can lose unsaved
   live-document work, so prefer waiting when the request may still finish.
4. **Do not fall back to GUI mode after a timeout.** Re-run the analysis in the worker
   (`read_only=true`, `execution_mode="worker"`, an explicit `timeout_seconds`) once a
   liveness check passes.

## 4. Deferred: containerized FreeCADCmd worker (design note, not built)

The native worker (`worker_manager.py`) already provides real process isolation and an
enforceable hard timeout: it snapshots open documents on the GUI thread, runs
`worker_entry.py` in a separate `FreeCADCmd.exe`, and kills the process tree (via a Windows
job object) if the timeout expires. **A container does not move live-document execution off
the GUI thread and would not have prevented this incident**, so it is deferred.

If host-level isolation is later desired, a container worker should preserve the existing
`worker_manager` contract:

- Snapshot open documents on the GUI thread exactly as today; mount the snapshot workspace
  read-write into the container (the workspace is disposable).
- Run the same `worker_entry.py --pass job.json` inside the image, using the container's
  `freecadcmd`. The image already exists for tests (see `Dockerfile.freecad-test` in the
  AutoCurtains project, which builds a conda `freecad` env); reuse that base.
- Enforce the hard timeout by stopping/removing the container (equivalent to
  `terminate_process_tree`), and read `result.json` back from the mounted workspace.
- Keep the version-compatibility check (`require_compatible_builds`) between the GUI build
  and the container's FreeCAD so snapshots reopen faithfully.

Note: `compose.freecad-test.yml` in the AutoCurtains project is a document-stability **test**
harness (`pytest`), not an MCP serving path; it does not wrap the MCP server or the worker.
