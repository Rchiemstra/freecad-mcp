# Per-document agent leases

FreeCAD MCP uses renewable, per-document write leases to keep cooperative MCP
agents from editing the same document concurrently. A lease does not make
FreeCAD a sandbox; it authenticates and fences MCP mutations, makes ownership
visible, and retains recoverable state when work cannot finish cleanly.

## Modes

`document_lease_mode` in `freecad_mcp_settings.json` controls the policy:

- `off`: legacy local behavior. A recognized active v2 sidecar still blocks an
  updated addon from ignoring another instance's ownership.
- `observe`: display and report ownership without requiring a local lease for
  every legacy mutation. Foreign v2 ownership still blocks.
- `enforce`: protocol v2 authentication and an exact lease credential are
  mandatory for every cooperative mutation. Isolated profiles use this mode.

The old `enable_document_lock` and `document_lock_enforcement` keys remain only
for migration. Both true maps to `enforce`, lock enabled alone maps to
`observe`, and all other legacy combinations map to `off`. New ordinary
profiles default to `observe`; isolated profiles are generated as `enforce`.
Malformed or unknown policy values block RPC startup rather than silently
downgrading. New configuration should use `document_lease_mode`.

The validated mode is latched when the process-level lease runtime starts.
Editing, deleting, or corrupting the settings file cannot downgrade a running
enforce listener. Runtime reinitialization rejects every mode change while an
active lease or recovery record exists.

## Lifecycle

1. The MCP client authenticates to the exact addon profile/runtime.
2. `acquire_document_lock` resolves a clean live FreeCAD document and returns a
   256-bit token once. The addon retains only its SHA-256 fingerprint. A
   document that was already dirty must instead use `adopt_dirty_document`;
   the addon auto-authorizes adoption without a FreeCAD pop-up, including an
   automatic handoff from another agent's dirty ``LOCKED_ERROR`` lease. The
   handoff revalidates the live document before atomically rotating authority.
   The addon creates an owner-only recovery `saveCopy` before returning the
   one-time credential. Adoption does not save or recompute the live document.
3. Every mutation declares the document session UUID and sends the lease ID,
   generation, and token in an immutable request envelope.
4. Authorization is checked before queueing and again on FreeCAD's GUI thread
   immediately before the mutation.
5. The addon owns state transitions around editing, recompute, validation, and
   saving. Heartbeats renew time only; clients cannot choose state.
6. A clean release requires an unmodified, validated, verified save and
   compare-and-remove of the adjacent sidecar.

Save As uses a crash-recoverable two-sidecar handoff. The destination is
reserved first, both records are linked by a random migration UUID plus exact
source/destination path identities, and the source is removed only after the
verified destination is authoritative. A final destination CAS clears the
linkage; failure at any boundary remains locked or error rather than reporting
success. After a crash, foreign status can correlate surviving records by the
redacted migration ID and roles, but never clears them automatically.

Normal modelling moves through `ACQUIRING`, `LOCKED_IDLE`,
`LOCKED_EDITING`/`LOCKED_RECOMPUTING`, `LOCKED_SAVING`, `RELEASING`, and
`UNLOCKED_SAVED`. Uncertain or failed work remains visible as `LOCKED_ERROR`,
`STALE`, `USER_INTERVENED`, or `UNLOCKED_DIRTY` until it is resolved.

Heartbeats run every 10 seconds with jitter, disk renewal is coalesced to 30
seconds, and a 90-second gap becomes `STALE`. A clean, fully save-verified
`LOCKED_IDLE` lease may also become `STALE` with `LEASE_OWNER_EXITED` without
waiting for that gap when host, boot, process-start, profile, addon-runtime, and
FreeCAD-runtime evidence positively proves that its co-located,
credential-owning MCP process exited. A replacement MCP in that same live
runtime may acquire only after a core-authorized recovery snapshot, fresh
clean-document validation, exact saved-baseline hash and identity verification,
and guarded generation/credential rotation. When core authority is available,
success also requires exact owner, generation, and provider read-back; a
mismatch republishes the prior lease authority at newer revisions and returns
no credential. Remote, live, or unknown owner evidence remains blocking. The
narrowly recognized pre-fix worker-snapshot
`USER_INTERVENED` signature does not need process-death proof because takeover
already rotated its generation and digest to a discarded secret. Stale never
means automatically safe to delete or reuse.

If an imported foreign record was cached before its sidecar disappeared, that
local worker-signature shortcut is not trusted. The addon must prove the
recorded foreign FreeCAD authority inactive, independently re-hash the saved
baseline, and snapshot the exact live proxy. Clean state can then self-recover
through `acquire_document_lock`; dirty state must use `adopt_dirty_document`
and remains dirty. Atomic sidecar creation, verified core fencing, and private
credential escrow complete before the immutable foreign cache is replaced.

The public lifecycle tools are `acquire_document_lock`,
`adopt_dirty_document`, `get_document_lock`, `list_document_locks`,
`update_document_lock`, `save_document`,
`save_document_as`, `finalize_document_edit`, and the lease-aware snapshot and
restore tools. Heartbeat batching and reconciliation are authenticated internal
control operations. Force release is deliberately absent from ordinary MCP
tool exposure.

Every typed lifecycle selector exposes exactly three accepted keys:
`document_name`, `document_session_uuid`, and `canonical_path`. At least one is
required. Supplying several makes them identity assertions, so they must all
resolve to the same open document. Fields such as `name`, `document`, and
`doc_name` are rejected by the tool schema and the addon RPC boundary.

## Modelling and reads

A PartDesign task may keep one lease while it creates a Body, attaches a
Sketch, adds geometry and constraints, creates Pad/Pocket features, validates
Body membership and Tip, saves, reopens for verification, and releases. Each
individual live mutation is still a separate GUI-thread transaction.

Arbitrary `read_only=True` code runs against an immutable FreeCADCmd snapshot,
not the live GUI document. Public arbitrary live mutation is disabled in
enforce mode unless the explicit unsafe policy is enabled; that policy is a
scope check, not a Python sandbox. The worker remains snapshot-only and never
mutates a leased live document; see the
[RPC worker architecture](freecad_rpc_worker_architecture_plan.md). Snapshot
creation attributes only the exact synchronous `saveCopy` start and finish
callbacks for its request, document proxy, and normalized target path. Other
save paths and all non-save observer callbacks remain subject to normal
intervention fencing.

## User intervention

The status-bar indicator and optional dock show owner, operation, elapsed time,
heartbeat age, and dirty/error state without changing `Document.Label`.
Selecting and inspecting remain available. A confirmed Take Over action
increments the fencing generation and revokes the old agent token. The old
agent cannot heartbeat back into ownership or reacquire automatically.

FreeCAD's Python observers notify after some changes and do not universally
veto Python console, macro, third-party C++, undo/redo, edit-mode, or close
paths. Known GUI commands are deterred and unexpected changes fence the agent,
but absolute in-process immutability would require a FreeCAD core mutation-veto
API.

See [sidecar schema](document-lease-sidecar-v2.md),
[recovery](lease-recovery.md), [security](lease-security.md), and
[client scenario diagrams](lease-client-scenarios.md), and
[isolated setup](isolated-instance.md).
