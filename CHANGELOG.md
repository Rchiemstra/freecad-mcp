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
- Fixed cached foreign authority becoming permanently circular after its
  sidecar disappeared. A fully verified clean record, or the exact legacy
  worker-snapshot `USER_INTERVENED` false-positive, can now repair exact-proxy
  identity drift and self-recover without closing the document. Dirty state
  remains dirty and requires `adopt_dirty_document`; recovery snapshots first,
  re-hashes the saved baseline, proves the foreign FreeCAD authority inactive,
  atomically creates higher-generation authority, verifies the core fence, and
  escrows the raw credential before replacing the foreign cache. Sidecar
  create/delete now report typed post-publication uncertainty so cross-layer
  rollback cannot silently strand authority.
- Made `LOCKED_ERROR` a resumable fence: the credential owner may retry
  health-checked typed mutations, and a different MCP process may continue a
  dirty errored document through confirmed atomic credential handoff.
- Added guarded restart recovery for a foreign dirty `LOCKED_ERROR`: after
  proving the recorded FreeCAD process dead and the saved FCStd still exactly
  matches the original lease baseline, a normal acquire atomically fences the
  stale authority into a higher generation even if the old MCP client process
  is still running.
- Fixed same-runtime orphaned leases: when a positively co-located,
  credential-owning MCP process is proven dead, a replacement MCP in the same
  live addon/FreeCAD runtime may recover a fully save-verified clean lease.
  The pre-fix worker-snapshot `USER_INTERVENED` signature is also recoverable
  because takeover already irrevocably rotated its credential. Recovery takes
  a core-authorized snapshot under the old fence before fresh document/file
  validation and one guarded higher-generation rotation. On patched FreeCAD,
  the new credential is returned only after core owner/generation/provider
  read-back matches the sidecar and the raw token is secured in the private
  claim vault. A core or escrow mismatch logically restores the prior authority
  at newer revisions; cancellation is rejected only after crossing this
  rollback-or-escrow boundary. Unacknowledged credentials no longer expire,
  yield vault capacity, or get rejected at the vault's soft capacity. A
  post-publication sidecar error continues after an exact guarded read—or with
  an explicit uncertainty warning when that read is unavailable—so the known
  published successor always receives matching core authority and an escrowed
  raw token. A mismatched read or incomplete/uncertain cross-layer rollback
  retains the recovery snapshot. Live, remote, unknown, changed,
  intentional-takeover, and concurrent authority still fails closed.
- Fixed worker snapshot `saveCopy` callbacks being mistaken for user saves.
  Only the exact synchronous request/document/target save callbacks are
  attributed internally; unrelated saves and mutation callbacks remain fenced,
  and non-owner snapshots receive only the core's narrowly scoped,
  current-generation `SaveAs` capability.
- Fixed the silent-build bounding-box guard to measure distance outside the
  box instead of distance to its nearest face, eliminating false failures for
  profile origins that are correctly inside a feature.
- Fixed GUI dispatch starvation after startup when Qt retained an invisible
  stale popup/modal pointer; only visible overlays now defer queued GUI work.
- Preserved lease, isolated-instance, worker, snapshot, and remote-RPC security
  behavior while retaining readable text and legacy worker-code aliases.
