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
- Preserved lease, isolated-instance, worker, snapshot, and remote-RPC security
  behavior while retaining readable text and legacy worker-code aliases.
