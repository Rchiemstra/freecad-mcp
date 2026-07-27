# FreeCAD MCP Improvement Result

## Summary

Phases A through I of `doc/freecad_mcp_unified_improvement_plan.md` are
implemented on the current branch. The result adds derived MCP/addon identity,
schema-v1 structured outcomes, correlated and redacted JSONL telemetry,
bounded document-health validation, explicit transaction/rollback evidence,
typed request lifecycle handling, negotiated MCP Tasks with synchronous
fallback, a 20-task benchmark and KPI report, execute-code migration analysis,
and the required operator/developer documentation.

The final source image passed the Docker unit, e2e, core, and benchmark suites.
All benchmark quality gates passed. No pull request or commit was created.

## Baseline commit

- Branch: `main`
- Actual branch HEAD used as the implementation baseline:
  `8ce7adefcf87a8e0abe86e4844123eb7f14b9db5`
- Baseline recorded in the supplied plan:
  `a474f3889b62e826028b3bd20ece390f438f1393`

The plan's inspected commit did not match the current branch HEAD. Existing
current-branch history was preserved and all implementation work was applied
to the actual HEAD above.

## Changed architecture

- `build_info` is the single source of MCP package identity; the independently
  installable addon has matching bundled/environment-injected metadata.
- `InstrumentedFastMCP` owns tool correlation, validation/tool lifecycle
  telemetry, result-schema advertisement, MCP SDK compatibility, and optional
  task-augmented execution.
- All response helpers produce readable text plus authoritative normalized
  `structuredContent`.
- Context-local telemetry connects MCP calls to authenticated RPC requests,
  GUI executions, worker jobs, document sessions, transactions, cancellation,
  and recovery incidents.
- The addon mutation boundary captures bounded health snapshots, executes
  mutations inside explicit transactions where supported, validates before
  commit, aborts degraded attempts, and reports final health and rollback
  evidence.
- GUI and worker lifecycle classification uses stable codes and state rather
  than diagnostic-string parsing. Inflight/replay records back request status,
  cancellation, late completion, expiry, and recovery.
- Benchmark tasks, validators, KPI calculation, quality gates, baseline
  comparison, and report generation are isolated under `benchmarks/` and the
  Docker `benchmark` service.
- Public Python is AST-classified without storing source, separated from
  generated internal execution, and matched to preferred typed tools where
  evidence supports a recommendation.

## Changed files

Modified existing files (33):

```text
.gitignore
Dockerfile
README.md
addon/FreeCADMCP/rpc_server/gui_dispatcher.py
addon/FreeCADMCP/rpc_server/inflight_requests.py
addon/FreeCADMCP/rpc_server/lease_protocol.py
addon/FreeCADMCP/rpc_server/mutation_guard.py
addon/FreeCADMCP/rpc_server/rpc_server.py
addon/FreeCADMCP/rpc_server/worker_manager.py
docker-compose.yml
pyproject.toml
scripts/start_freecad_isolated.py
src/freecad_mcp/debug_log.py
src/freecad_mcp/freecad_client.py
src/freecad_mcp/operations/core.py
src/freecad_mcp/operations/diagnostics.py
src/freecad_mcp/operations/interactive.py
src/freecad_mcp/operations/p1_curves.py
src/freecad_mcp/operations/p2_editing.py
src/freecad_mcp/operations/p3_features.py
src/freecad_mcp/operations/p7_assembly.py
src/freecad_mcp/operations/snapshot.py
src/freecad_mcp/responses.py
src/freecad_mcp/server.py
src/freecad_mcp/server_state.py
tests/conftest.py
tests/e2e/test_rpc_lifecycle.py
tests/e2e/test_worker_process.py
tests/test_lease_protocol.py
tests/test_reference_repair_tools.py
tests/test_rpc_sync.py
tests/test_worker_manager.py
tests/test_worker_queue.py
```

Added files (42, including this report):

```text
CHANGELOG.md
addon/FreeCADMCP/_build_metadata.json
addon/FreeCADMCP/build_info.py
addon/FreeCADMCP/rpc_server/execute_code_analysis.py
addon/FreeCADMCP/rpc_server/telemetry.py
benchmarks/__init__.py
benchmarks/fixtures/README.md
benchmarks/report.py
benchmarks/runner.py
benchmarks/tasks/__init__.py
benchmarks/tasks/catalog.py
benchmarks/validators/__init__.py
benchmarks/validators/core.py
doc/benchmarking.md
doc/document-health.md
doc/execute-code-migration.md
doc/freecad_mcp_improvement_result.md
doc/request-lifecycle.md
doc/runtime-identity.md
doc/structured-results.md
doc/telemetry.md
doc/transactions-and-rollback.md
scripts/analyze_mcp_telemetry.py
scripts/generate_build_metadata.py
scripts/merge_mcp_telemetry.py
src/freecad_mcp/build_info.py
src/freecad_mcp/instrumented_server.py
src/freecad_mcp/mcp_tasks.py
src/freecad_mcp/outcomes.py
src/freecad_mcp/telemetry/__init__.py
src/freecad_mcp/telemetry/context.py
src/freecad_mcp/telemetry/events.py
src/freecad_mcp/telemetry/legacy_parser.py
src/freecad_mcp/telemetry/redaction.py
src/freecad_mcp/telemetry/schema.json
src/freecad_mcp/telemetry/writer.py
tests/benchmark/test_benchmark_tasks.py
tests/test_benchmark_reporting.py
tests/test_build_info.py
tests/test_document_health.py
tests/test_mcp_tasks.py
tests/test_telemetry.py
```

The generated, ignored runtime artifacts are `benchmark-results.json` and
`benchmark-report.md`.

## Structured result model

Every response helper returns `CallToolResult` with concise text and a
schema-v1 envelope in `structuredContent`. Normalized statuses are
`succeeded`, `condition_false`, `warning`, `degraded`, `rejected`, `failed`,
`timed_out`, `cancelled`, and `unknown`. The envelope carries cross-layer
status, correlation, execution, transaction, document-health, mutation-scope,
and backend data when applicable.

Valid negative observations such as an unsynchronized-but-well-formed nonce
probe use `condition_false` and are not MCP errors. Malformed data, nonce
mismatch, and transport failures remain errors. Backend codes and structured
diagnostics survive operation adaptation. Image content remains in MCP image
blocks and is excluded from structured JSON.

The wrapper also corrects MCP SDK output-schema inference: tool discovery
advertises the result envelope rather than the outer `CallToolResult` model.
SDK-specific registration options and older memory-transport behavior are
adapted without changing tool implementations.

## Telemetry events

Schema-v1 JSONL includes microsecond UTC time, monotonic nanoseconds,
per-session sequence, source/event/status, duration, error code, and all
applicable correlation identifiers. Lifecycle coverage includes session,
authentication, validation, policy, routing, RPC, GUI, worker, transaction,
health, cancellation, recovery, and terminal tool events.

MCP and addon writers use independent per-process/session files, flush each
line, rotate with bounded backups, and tolerate write failures. Redaction
removes credential-shaped fields and exact discovered secret values, replaces
code and image bodies with hash/byte summaries, and caps payload size with
truncation metadata. Merge, migration-only legacy parsing, and analysis tools
are included.

## Document-health behavior

Health profiles `none`, `minimal`, `default`, and `full` control validation
cost. Snapshots and deltas report recompute/state/shape/Body-Tip issues plus
created, deleted, modified, and unexpected objects where measurable.
Pre-existing errors are separated from newly introduced errors.

Typed mutation results include a health verdict. Healthy expected changes
remain `healthy`; preserved pre-existing issues produce `warning`; new
recompute, state, shape, or Body-Tip issues produce `degraded`; failed
recompute/save/reopen/restore produces `invalid`; skipped or unavailable
validation is reported as `unknown`. Default validation remains bounded to
affected/created geometry rather than validating every shape.

Save/finalize paths include reopened-document evidence. Unexpected changes in
unrelated documents are surfaced and degrade the result.

## Transaction and rollback behavior

`GuiMutationTransaction` reports enablement, documents, start/commit state,
abort attempt/result, and every abort error. On headless FreeCAD builds with
undo disabled, the transaction temporarily enables undo and restores the
original preference so an abort actually restores document state.

Typed mutations now follow capture, open, execute, recompute, validate, then
commit. Tool failure, exception, or degraded postflight aborts before commit;
final health is captured after abort. Rollback failure produces
`TRANSACTION_ROLLBACK_FAILED` and degraded/invalid evidence.

Coverage is explicitly `complete`, `document_only`, `partial`, or
`unavailable`. Save/export/filesystem effects do not claim document-transaction
coverage. Public arbitrary Python defaults to unavailable rollback with policy
`none`; signed generated operations inherit the actual typed mutation context.

## Timeout, cancellation, and recovery behavior

GUI dispatch raises typed exceptions carrying code, timeout stage, request ID,
execution/mutation start, and completion uncertainty. Worker lifecycle returns
stable uppercase codes while retaining legacy aliases for compatibility.

`get_request_status` and `cancel_request` expose queued, running,
running-after-timeout, completed, failed, cancel-requested, cancelled,
completed-after-cancel-request, unknown, and expired states. The replay cache
retains bounded expiry tombstones. Cancellation before mutation and
cancellation after mutation begins remain distinguishable.

Timeouts that leave completion uncertain create a recovery incident. Late
completion, synchronization, cancellation, and reconciliation remain linked
to the original request and incident. Negotiated MCP Tasks wrap candidate
heavy operations, map task IDs to existing request/worker IDs, bridge
cancellation to the authenticated request, and preserve synchronous fallback.

## Benchmark results

The final Docker benchmark passed 20 of 20 tasks and all encoded quality gates.
It exercised live FreeCAD document/geometry/save/reopen/snapshot behavior,
transaction rollback, policy/scope guards, lifecycle classifications, public
compatibility execution, and typed addon execution.

- Results: `benchmark-results.json`
- Markdown: `benchmark-report.md`
- FreeCAD: `1.1.0`, revision `20260325 (Git shallow)`
- MCP SDK in the final image: `1.28.1`
- Prior benchmark supplied: no; this run establishes the baseline
- Regression flags: 0

## KPI comparison

| KPI / gate | Required | Final |
|---|---:|---:|
| Benchmark task success | >= 90% | 100% |
| First-attempt success | >= 85% | 100% |
| Tool execution success | >= 98% | 100% |
| Completed response rate | measured | 100% |
| Argument validity | >= 97% | 100% |
| Tool selection accuracy | measured | 100% |
| Protected rejection rate | measured | 100% |
| Safe failure rate | >= 99% | 100% |
| False-positive rejection | measured | 0% |
| Unexpected runtime failure | measured | 0% |
| Recovery success | measured | 100% |
| Rollback success | measured | 100% |
| Save/reopen validation | 100% | 100% |
| Document-health regressions | 0 by default | 0% |
| Unrelated-document mutation | 0 | 0% |
| Committed new recompute errors | 0 | 0 |
| Unclassified failures | 0 | 0 |
| Unexpected non-task timeout | < 1% | 0% |
| Public execute-code share | < 50% initial | 2.7027% |
| Typed-tool share | measured | 91.8919% |
| Generated internal execute share | measured separately | 11.9048% |
| Calls per successful task | measured | 1.85 |
| Token metric coverage | optional client input | 0% / `null` |

Expected timeout/cancellation tasks account for 5% at the GUI stage and 5% at
the worker stage; they are successful safety scenarios and are excluded only
from the separate unexpected-non-task timeout gate.

Final p50 latency by execution class was 1.025 ms public execute,
0.886 ms read-only worker analysis, and 9.751 ms typed direct RPC. Final p95
was 1.025 ms, 1.628 ms, and 492.195 ms respectively.

## Execute-code adoption results

Terminal telemetry and benchmark KPIs distinguish
`public_execute_code`, `generated_internal_execute`, `typed_direct_rpc`,
`read_only_worker_analysis`, and `deprecated_execute_code_async`. Result-level
categories override the generic MCP verb so worker and signed-generated calls
are not miscounted as public Python.

Public calls are grouped by imported APIs, operations, declared document
scope, read-only/mutating mode, GUI/worker target, repeated AST pattern,
outcome, latency, source/AST hashes, and typed-tool suggestions. Reports never
store raw code. Known matches add `TYPED_TOOL_AVAILABLE`; generated internal
operations suppress that warning.

The benchmark's public-code share is 2.7027%, below both the initial 50% and
mature 25% targets. No additional dedicated typed tool was added because the
benchmark/telemetry evidence did not establish a repeated unsupported public
pattern with a stable schema and meaningful safety benefit.

## Tests executed

```text
Host compile:
  python -m compileall -q src addon benchmarks scripts tests
  PASS

Host unit:
  python -m pytest -m unit -ra --tb=short
  1238 passed, 32 skipped, 5 deselected, 1 xfailed

Docker build:
  docker compose build
  PASS

Docker unit:
  docker compose run --rm unit
  1249 passed, 3 skipped, 122 deselected, 1 xfailed

Docker e2e:
  docker compose run --rm e2e
  111 passed, 1264 deselected

Docker core:
  docker compose run --rm core
  3 passed, 1365 deselected, 7 xfailed

Docker benchmark:
  docker compose run --rm benchmark
  1 suite passed; 20/20 tasks and all quality gates passed

Repository checks:
  git diff --check
  PASS (line-ending conversion notices only)
```

Focused suites also covered runtime identity, telemetry schema/redaction,
document health, transaction behavior, request/task lifecycle, SDK 1.26/1.28
compatibility, benchmark reporting, and execute-code classification.

## Known limitations

- The unit suite retains one pre-existing expected failure for the P10/I10
  no-screenshot structured-diff behavior, which is outside this plan.
- The core suite retains seven expected FreeCAD runtime/upstream failures:
  constraint signatures, cross-body datum placement, shape-placement
  absorption, joint/datum behavior, body-removal orphaning, and Part.Circle
  direction aliases. They are documented guards, not MCP regressions.
- Default health validation is intentionally bounded. Full all-shape and
  save/reopen validation is reserved for full/checkpoint profiles.
- Public mutating Python and external filesystem effects cannot offer complete
  rollback. Their results state `unavailable` or `partial` rather than
  overstating safety.
- `execute_code_async` remains available only in off/observe compatibility
  modes and remains deprecated; enforcement blocks it.
- MCP Tasks depend on negotiated SDK/client support. Unsupported clients use
  the tested synchronous path.
- Exact token KPIs require counts from an MCP client. No client token input was
  supplied, so token coverage is zero and tokens-per-success remains `null`.
- No prior benchmark JSON was supplied, so this is the first KPI baseline
  rather than a historical before/after measurement.
- Source/editable builds use the deterministic `+unknown` build fallback unless
  release/CI metadata or documented environment variables are injected.

## Follow-up recommendations

1. Preserve `benchmark-results.json` from this run as the comparison input in
   CI and fail future builds on the existing regression flags and gates.
2. Generate matching MCP/addon build metadata in release jobs with
   `scripts/generate_build_metadata.py`.
3. Feed client-provided token counts into benchmark observations when the MCP
   client exposes them.
4. Monitor `scripts/analyze_mcp_telemetry.py` output and add a dedicated typed
   tool only when a repeated public pattern satisfies the evidence gates.
5. Track or upstream the seven FreeCAD core xfails and retire MCP guardrails
   only after the target runtime contains verified fixes.
