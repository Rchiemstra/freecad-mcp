# Lease security model

Document leases protect cooperative multi-agent modelling from accidental
cross-document or concurrent writes. They are not an operating-system sandbox
and do not make arbitrary code inside FreeCAD trustworthy.

## Guarantees

- Protocol-v2 sessions authenticate a client to one profile/runtime using a
  per-profile 256-bit secret, nonces, and HMAC-SHA-256.
- Every mutation carries an immutable request ID and exact per-document lease
  credentials. Authorization is repeated on FreeCAD's GUI thread.
- Request IDs are journaled by authenticated MCP runtime, not by the renewable
  RPC session. A completed mutation therefore cannot run again after session
  refresh or listener restart. Mutation entries remain pinned while that
  runtime has any unresolved lease/recovery record; after ten minutes their
  result is reduced to a secret-free `REQUEST_ALREADY_COMPLETED` tombstone,
  while the request fingerprint remains authoritative.
- Raw lease tokens remain in MCP/addon memory. Only SHA-256 fingerprints enter
  sidecars; public status and logs omit both token and fingerprint.
- Task descriptions remain process-local by default. Sidecars contain an empty
  task summary unless `persist_task_summary_in_sidecar=true` explicitly opts
  into a sanitized, single-line, 256-character diagnostic summary.
- Fencing generations prevent an old owner from resuming after intervention or
  takeover.
- Adjacent sidecars use guarded compare-and-swap and owner-only permissions.
  Registry/sidecar disagreement blocks instead of selecting the more
  permissive state.
- Dirty, uncertain, stale, malformed, and save-failed states remain visible and
  locked until explicitly resolved.

## Non-goals and residual risk

- FreeCAD observers do not universally veto Python console commands, macros,
  third-party addons, C++ commands, undo/redo, task entry, or document close.
  Known GUI actions are deterred and unexpected changes revoke the agent after
  detection, but absolute in-process immutability needs a FreeCAD core API.
- A malicious process running as the same OS user can read the profile secret,
  call FreeCAD directly, or damage sidecars. Owner-only files reduce accidental
  exposure; they are not same-account isolation.
- Sidecars cannot discover every hardlink alias on every host. Canonical paths
  and filesystem identities reduce this risk.
- FreeCAD mutation and filesystem metadata cannot form one atomic transaction.
  Crash handling therefore prefers leftover locks over an unsafe unlocked
  interval.

## Secret and transport handling

`setup_isolated_profile.py` creates exactly 32 random bytes in
`freecad_mcp_auth.secret`, uses mode `0600` on POSIX, and removes inherited ACLs
on Windows. The manifest and Cursor configuration contain only its path. Never
paste, log, commit, or copy the secret into an MCP argument value.

HMAC authenticates but does not encrypt XML-RPC. Loopback is the default and
recommended deployment. A remote connection must use an SSH tunnel or TLS
proxy, a narrow IP/CIDR allowlist, and a separately protected secret. Plain
non-loopback XML-RPC exposes session and lease credentials to network observers.
Accordingly, `document_lease_mode=enforce` rejects a non-loopback addon bind
unless `allow_authenticated_remote_without_transport_security=true` is set by
an administrator as an explicit unsafe override. The ordinary GUI remote toggle
does not enable that override. Isolated-instance manifests reject non-loopback
addresses entirely; terminate the tunnel/proxy locally instead.

## Arbitrary code and workers

`read_only=True` arbitrary code must execute against a snapshot in FreeCADCmd,
not the live GUI document. Enforce mode disables public arbitrary live mutation
unless `allow_unsafe_mutating_execute_code` is explicitly enabled. Even then,
declared document scopes and before/after auditing are guardrails, not a Python
sandbox; dynamic imports or native extensions can escape source inspection.

Worker snapshot files and recovery snapshots may contain proprietary model
data. Keep the profile and recovery directory owner-only, bound retention, and
remove artifacts only after the associated lease is safely finalized.

## Availability and recovery

An attacker or faulty process can create locks, starve heartbeat/control lanes,
or fill storage. Force release is intentionally a local, confirmed recovery
operation rather than an ordinary MCP tool. Rate-limit authentication failures,
do not log heartbeat secrets, and follow [lease recovery](lease-recovery.md)
instead of deleting old sidecars automatically.

The request journal is intentionally bounded. It never evicts an in-progress
request or a mutation pinned by an unresolved lease. If protected entries fill
the journal, new mutations fail closed with `REPLAY_JOURNAL_FULL`; finalize or
locally resolve the owning leases instead of clearing journal state. Automatic
heartbeats and read-only requests are not lease-lifetime pinned.
