# Changelog

## 0.2.0

- Added canonical package/addon build identity and `get_runtime_info`.
- Added schema-v1 structured tool outcomes with normalized status/layer fields.
- Added correlated, redacted, per-process JSONL telemetry and analysis tools.
- Added document-health snapshots/deltas and validation profiles.
- Added explicit transaction, rollback, and coverage reporting.
- Added typed GUI/worker timeout codes, request status/cancellation, recovery
  incidents, late-completion correlation, and negotiated MCP Tasks fallback.
- Added the 20-task Docker benchmark, KPI reports, adoption categories, AST-only
  public-code analysis, and typed-tool migration guidance.
- Added lease-safe typed `sketch_delete_constraint` and
  `sketch_delete_geometry` operations with atomic batch validation.
- Added an explicit GUI-loop override to `sketch_add_external_projection` for
  its bounded assembly-aware preflight.
- Added guarded agent self-recovery for a saved `UNLOCKED_DIRTY` sidecar after
  restart, using dead-owner proof, clean acquisition or confirmed dirty
  adoption, a fresh file baseline, and atomic generation fencing instead of
  manual deletion.
- Made `LOCKED_ERROR` a resumable fence: the credential owner may retry
  health-checked typed mutations, and a different MCP process may continue a
  dirty errored document through confirmed atomic credential handoff.
- Added guarded restart recovery for a foreign dirty `LOCKED_ERROR`: after
  proving the recorded FreeCAD process dead and the saved FCStd still exactly
  matches the original lease baseline, a normal acquire atomically fences the
  stale authority into a higher generation even if the old MCP client process
  is still running.
- Fixed the silent-build bounding-box guard to measure distance outside the
  box instead of distance to its nearest face, eliminating false failures for
  profile origins that are correctly inside a feature.
- Fixed GUI dispatch starvation after startup when Qt retained an invisible
  stale popup/modal pointer; only visible overlays now defer queued GUI work.
- Preserved lease, isolated-instance, worker, snapshot, and remote-RPC security
  behavior while retaining readable text and legacy worker-code aliases.
