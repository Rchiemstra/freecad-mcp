# GUI + write lane session recovery — implementation handoff

**Status:** implemented; under iterative review (2026-08-09).
**Branch:** `feature/assembly-interference-detection`
**Parent repo HEAD at diagnosis:** `2ce26bae32` · **submodule HEAD:** `eb655ffb`

This document is written for an agent picking the work up cold. Everything needed
to implement and verify is here; you should not need to re-derive the diagnosis.
Read §2–§4 before touching code, and read §5 (traps) before running anything —
it contains three things that will waste your time or damage the user's running
FreeCAD if you skip them.

---

## 1. TL;DR

An MCP client process loses the GUI lane and the write lane permanently — while
plain reads keep working — because the addon can invalidate an RPC session in four
distinct ways, and the client only knows how to recover from one of them. Fix the
client's classification, parse the second refusal shape, refresh before expiry
instead of after failure, and lock all of it down with a contract test that fails
CI if the addon ever adds a fifth code.

Six work items, §6. Start with **WI-0** (reproduce before fixing).

---

## 2. Symptom

Reported verbatim by another agent:

> "the MCP's GUI lane is now refusing too, same degradation that killed the write
> lane. Reads still work; anything that touches the GUI or changes a document doesn't."

Recognisers:

- `get_object`, `get_objects`, `ping`, `get_instance_info` → fine.
- `get_gui_state`, `get_selection`, `get_report_view`, `activate_document`,
  `refresh_view`, screenshots → refuse.
- Anything mutating a document → refuses.
- Restarting the MCP client process fixes it. Restarting FreeCAD is not required.
  **That last property is the tell** — it means the fault is in per-MCP-process
  session state, not in FreeCAD or the addon.

This has recurred repeatedly. The last four commits on the branch are all
attempts in this area: `75a12cb9c1`, `d4a7ca60ab`, `45c3e616db`, `2ce26bae32`.
The goal here is to end the recurrence, not patch it a fifth time.

---

## 3. Why reads survive while GUI and writes die together

Both failing lanes pass through **one** gate. Reads bypass it entirely.

`addon/FreeCADMCP/rpc_server/methods/dispatch_helpers_ops/dispatch_core_enforcement_auth.py:53`

```python
def requires_authenticated_session(method, kind, VerbKind, read_only_execute):
    return (
        (kind == VerbKind.MUTATING and not read_only_execute)
        or method in AUTHENTICATED_METHODS
    ) and method not in {"handshake_v2", "invoke_v2"}
```

`AUTHENTICATED_METHODS` (same file, line 8) holds every actor-scoped GUI method:
`activate_document`, `animate_placement`, `capture_view_sequence`,
`capture_view_sequence_to_disk`, `get_active_screenshot`, `get_gui_state`,
`get_report_view`, `get_selection`, `open_document`, `refresh_view`,
`reload_document`, `repair_view_placements`, `select_subshapes`,
`set_section_view`, `set_tree_expanded` — plus the lease/save verbs.

A plain read is neither `MUTATING` nor in that set, so it answers unauthenticated.
**One gate failing therefore takes down GUI and writes together and leaves reads
healthy — exactly the reported shape.**

There are two entry paths into that gate, and they matter later:

| lane | entry point | on failure returns |
|---|---|---|
| plain RPC (GUI) | `dispatch()` → `elevate_rpc_session_identity_or_error` (`dispatch_core.py:28-37`) | `{"success": False, "error_code": X, "error": "<string>"}` |
| `invoke_v2` (writes) | `invoke_v2()` → `authenticate_envelope` (`v2_methods_ops/invoke_v2.py:36`) | `{"ok": False, "error": {"code": X, "message": …}}` |

Two different shapes. Remember that.

---

## 4. Root cause

### 4.1 The addon invalidates sessions four ways

Session TTL is **5 minutes** — `DEFAULT_SESSION_TTL_SECONDS = 5 * 60.0`,
`addon/FreeCADMCP/_shared/protocol/constants.py:37`.

`SessionManager.authenticate()`, `_shared/protocol/session_manager.py:139-162`,
raises exactly one of:

| condition | code |
|---|---|
| record present, past TTL | `SESSION_EXPIRED` |
| record missing (already pruned) | `INVALID_SESSION` |
| explicitly revoked | `SESSION_REVOKED` |
| token belongs to another MCP runtime | `SESSION_BINDING_MISMATCH` |

`authenticate_envelope()` (line 163) adds `MISSING_RUNTIME_BINDING` and its own
`SESSION_BINDING_MISMATCH`.

### 4.2 The client can only recover from one of them

`src/freecad_mcp/generated/capabilities/connection_methods/connection_invoke_v2_helpers.py:16`

```python
_SESSION_EXPIRED_CODES = frozenset({"SESSION_EXPIRED", "UNKNOWN_SESSION"})
```

Consumed at `connection_invoke_v2_ops.py:63` (remote-error path) and `:87`
(in-band error path); anything not in the set is re-raised or returned as a hard
failure, with no re-handshake.

**`UNKNOWN_SESSION` is emitted by nothing.** Repo-wide grep finds it only in that
one allowlist — not in the addon, not in `src/`, not in tests. The intended
"session gone → re-handshake" recovery is dead code. The code actually produced
for that case is `INVALID_SESSION`, which is **not** in the set.

So: `SESSION_EXPIRED` recovers. `INVALID_SESSION`, `SESSION_REVOKED`,
`SESSION_BINDING_MISMATCH` are permanent for the life of the MCP process.

### 4.3 Why `INVALID_SESSION` is the common case, not the rare one

`_prune_locked()`, `session_manager.py:234-243`:

```python
def _prune_locked(self, now_mono: float) -> int:
    expired_ids = [
        session_id
        for session_id, record in self._sessions_by_id.items()
        if now_mono >= record.expires_monotonic
    ]
    for session_id in expired_ids:
        record = self._sessions_by_id.pop(session_id)
        self._sessions_by_digest.pop(record.token_digest, None)
    return len(expired_ids)
```

It runs inside **every** `perform_handshake` (line 86) and prunes expired records
across **all** MCP runtimes, not just the handshaking one. Nothing else calls it —
there is no janitor thread.

Consequence:

1. Agent A authenticates → session S1.
2. Agent A goes idle past 5 minutes (chatting, or doing reads — reads do not
   refresh the session, they never touch the auth lane).
3. Agent B's MCP process starts and handshakes → `_prune_locked` **deletes S1**.
4. Agent A's next GUI or write call → record gone → `INVALID_SESSION` → not
   recoverable → **dead for the rest of Agent A's process life, reads still fine.**

Without step 3 you would get `SESSION_EXPIRED` and silent recovery. Multiple
agents against one FreeCAD is the normal working mode here, which is why this
keeps coming back and why it looks intermittent.

### 4.4 Second, independent defect: the GUI refusal shape is never parsed

`connection_invoke_v2_helpers.py:161-166`

```python
def invoke_v2_session_error_code(response: Mapping[str, Any]) -> str | None:
    error = response.get("error")
    if not isinstance(error, Mapping):
        return None
    error_code = error.get("code")
    return str(error_code) if error_code is not None else None
```

The plain-GUI lane returns `{"success": False, "error_code": X, "error": "<string>"}`
(§3 table). Here `response["error"]` is a **string**, so the function returns
`None` and no code — recoverable or not — is ever detected on that path. Fixing
§4.2 alone does not fix the GUI lane; both are required.

### 4.5 No proactive refresh

`src/freecad_mcp/server_ops/manifest_auth.py:123-133` stores
`session_expires_at` and installs a refresher:

```python
surfaces.state.rpc_session_expires_at = verified.session_expires_at
configure_rpc_session(conn, surfaces.state.rpc_session)
conn.configure_session_refresher(
    lambda: refresh_authenticated_connection(conn)
)
```

The refresher is **purely reactive** — it only fires from
`_refreshed_context()` after a failure is classified. The stored expiry is never
consulted before sending. Adding a pre-flight refresh removes the failure class
instead of recovering from it.

---

## 5. Traps — read before running anything

### 5.1 `setup_isolated_profile.py --port 9877` will clobber the user's live instance

Both scripts hardcode the profile directory:

- `scripts/setup_isolated_profile.py:30` — `PROFILE_NAME = ".freecad-mcp-isolated"`
- `scripts/start_freecad_isolated.py:53` — same constant

`--port` only changes the port **inside the same profile dir**. Running it would
rewrite `.freecad-mcp-isolated/instance-manifest.json` and
`freecad_mcp_settings.json` — the manifest the user's running FreeCAD (PID 8616,
port 9876) is bound to. There is no CLI or env override.

The user's instruction was explicit: **do not use or disturb the live FreeCAD
session.** So WI-5 must first add a `--profile-name` argument (or a
`FREECAD_MCP_PROFILE_DIR` env override) to both scripts, defaulting to the current
constant so existing behaviour is unchanged. Do that before any e2e work.

### 5.2 The `GENERATED — do not edit` banner is stale for `connection_methods/`

`src/freecad_mcp/generated/capabilities/connection_methods/*.py` carries
`"""GENERATED by freecad_mcp.capabilities.generator — do not edit."""`, but
`_read_connection_method_source()` (`src/freecad_mcp/capabilities/generator.py:410-418`)
reads the **generated file back** as the canonical body once it exists:

```python
generated_path = connection_methods_root() / f"{module_name}.py"
if generated_path.is_file():
    return relocated_connection_method_body(module_name)
hand_written_path = _hand_written_connection_methods_dir() / f"{module_name}.py"
```

Editing these files in place is therefore correct and survives regeneration.
Confirm with a generator re-run producing a no-op diff (§8.7). Do **not** go
hunting for a manifest that defines `_SESSION_EXPIRED_CODES` — there isn't one.

### 5.3 The FreeCAD-side test does not belong in `DocumentCommitCoordinator.cpp`

`tests/src/App/DocumentCommitCoordinator.cpp` is a pure type-trait/contract file —
it never builds a Document, and `commitOnDocumentThread` is not reachable from it.

The correct home is `tests/src/App/DocumentCollaborationService.cpp`, which
already has a fixture producing a real `RecomputeFailed` against a real Document.
See WI-6.

### 5.4 Version skew is *not* the cause — don't chase it

The running addon is current. Probing the live instance returns
`LEASE_PROTOCOL_REQUIRED` for `get_report_view`, not `method ... is not supported`
— and `dispatch()` resolves `getattr(self, method)` *before* the auth check
(`dispatch_core.py:25-28`), so an auth error proves the method exists. The addon
symlink (`.freecad-mcp-isolated/Mod/FreeCADMCP` → `addon/FreeCADMCP`) plus a
restart at 08:37 had already picked up the `eb655ffb` content before it was
committed at 08:41.

---

## 6. Work items

### WI-0 — Reproduce before fixing *(do this first)*

Write the reproduction from WI-3 test #2 and run it against the **unfixed**
client. It must fail with `INVALID_SESSION` reaching the caller.

**If it does not fail pre-fix, stop and report.** The diagnosis in §4 would be
wrong and the fix would be unjustified. Do not ship a fix for a bug you have not
watched fail.

### WI-1 — Classify every session code the addon can raise

**File:** `src/freecad_mcp/generated/capabilities/connection_methods/connection_invoke_v2_helpers.py:16`

Replace the two-element set with an explicit recoverable set covering what the
addon actually emits:

- `SESSION_EXPIRED`
- `INVALID_SESSION`  ← the bug
- `SESSION_REVOKED`
- `SESSION_BINDING_MISMATCH`
- `UNKNOWN_SESSION` (retain for forward compatibility)

`LEASE_PROTOCOL_REQUIRED` is **conditionally** recoverable: retry only when the
client currently holds a session token. Bare-retrying it would mask genuine
"no credentials configured" misconfiguration, which is the other thing it means.

Keep the existing single-retry-per-call structure. Do not add a retry loop.

**Acceptance:** WI-0's reproduction passes; WI-3 tests #1–#3 pass.

### WI-2 — Parse both refusal shapes

**File:** same, `invoke_v2_session_error_code()` at line ~161.

Read a top-level `error_code` in addition to `error.code`, so the
`{"success": False, "error_code": X, "error": "<str>"}` shape from
`elevate_rpc_session_identity_or_error` / `authenticate_session_or_error` is
detected. Keep the existing `error.code` branch working.

The `JsonRpcRemoteError` path already lifts `data["error_code"]` into
`semantic_code` (`_shared/protocol/json_rpc_client.py:64-66`) — that one is
already correct; lock it in with a test rather than changing it.

**Acceptance:** WI-3 test #4 passes; WI-3 test #5 passes for the plain-dispatch lane.

### WI-3 — Refresh before expiry

**Files:** `connection_invoke_v2_helpers.py` (pre-flight check),
`src/freecad_mcp/server_ops/manifest_auth.py` (expose `expires_at`).

The client already has `RpcAuthenticationSession.expires_at`
(`src/freecad_mcp/rpc_session.py:85-88`). Before sending an authenticated call,
if expiry is within a ~60s skew margin, re-handshake first via the existing
`conn._session_refresher`. Keep the reactive retry as the safety net.

Note `expires_at` is an ISO-8601 UTC string; parse defensively and treat an
unparseable or empty value as "do not proactively refresh" rather than raising.

**Acceptance:** WI-3 test #7 passes; the soak test (WI-5) shows zero refusals.

### WI-4 — Auth-gate refusal diagnostics

**File:** `addon/FreeCADMCP/rpc_server/methods/dispatch_helpers_ops/dispatch_core_enforcement_auth.py`

Emit a debug-log event on every auth-gate refusal carrying the real protocol code
and which lane refused (GUI vs mutation). Today the refusal is invisible in
`debug_logs/` — recovering the diagnosis in §4 required static analysis. After
this, a recurrence is answerable from the log.

Use the existing telemetry surface (`src/freecad_mcp/debug_log.py`,
`src/freecad_mcp/telemetry/`); follow how `execute_code` emits `routing_completed`
records in `addon_debug_*.jsonl`.

Also: when a re-handshake itself fails, surface an error naming the addon's
protocol code and the lane rather than a generic failure — extend the
`unwrap_nested_remote_error` work from `715ccc10`.

**Acceptance:** a forced refusal produces a `debug_logs/` record containing the
protocol code.

### WI-5 — Test suites *(detail in §7)*

### WI-6 — FreeCAD-side structural refusal gtest

**File:** `tests/src/App/DocumentCollaborationService.cpp` (parent repo)

`2ce26bae32` enriched `DocumentCommitCoordinator::commitOnDocumentThread` so a
`RecomputeFailed` names each invalid object and its error description:

```cpp
std::ostringstream detail;
detail << "document recompute reported an object error";
bool first = true;
for (App::DocumentObject* object : _document.getObjects()) {
    if (!object || object->isValid()) { continue; }
    detail << (first ? ": " : ", ");
    first = false;
    const char* name = object->getNameInDocument();
    detail << (name && *name ? name : "<unnamed>");
    if (const char* why = _document.getErrorDescription(object); why && *why) {
        detail << " (" << why << ")";
    }
}
```

It shipped with **no test**. This is the C++ half of keeping an agent unblocked:
a refusal that names the offending object lets the agent act instead of retrying
blindly.

Extend the existing fixture test at
`tests/src/App/DocumentCollaborationService.cpp:1477`,
`DocumentCollaborationServiceTest.recomputeFailureRestoresPreparedMutation`,
which already drives a real `RecomputeFailed` against an object named `Target`.
Assert `result.message` (field declared at `src/App/DocumentCommitCoordinator.h:41`)
names `Target` and carries its error description — rather than the bare
`"document recompute reported an object error"` it used to return.

Prefer a new sibling `TEST_F` over overloading the existing one, so a failure
message points at the right concern.

**Acceptance:** the new gtest fails against the pre-`2ce26bae32` message and
passes at HEAD.

---

## 7. Test specifications

All committed to the repos — no scratch scripts. **No test may touch the live
instance on port 9876 or the `.freecad-mcp-isolated` profile.**

### 7.1 Unit — `tests/test_session_recovery_contract.py` (new, marked `unit`)

1. **Anti-drift contract test — this is the one that stops the recurrence.**
   Enumerate every `ProtocolError` code reachable from `authenticate()` and
   `authenticate_envelope()` and assert each is *explicitly* classified as
   recoverable or terminal by the client. A new code added to the addon without a
   classification must fail CI. Derive the code list from the addon source rather
   than hardcoding it, so the test cannot silently drift.
2. **The reported bug.** Handshake → expire → prune (via a second
   `perform_handshake`) → authenticated call → assert the client re-handshakes and
   the call succeeds. Assert the caller never sees `INVALID_SESSION`.
3. Revoke → `SESSION_REVOKED` → recovery. Runtime rebind →
   `SESSION_BINDING_MISMATCH` → recovery.
4. Both refusal shapes are detected by `invoke_v2_session_error_code`:
   `{"error": {"code": X}}` and `{"success": False, "error_code": X, "error": "<str>"}`.
5. **Parametrized over the entire `AUTHENTICATED_METHODS` set** so no GUI method
   is left behind — both the plain `dispatch` lane and the `invoke_v2` lane must
   recover for every member. Import the set; do not copy it.
6. Cross-runtime regression: a second MCP runtime's handshake must not leave the
   first runtime unable to recover (§4.3).
7. Proactive refresh fires inside the skew margin and does not fire outside it.
8. `LEASE_PROTOCOL_REQUIRED` retries when a session token is held and does **not**
   retry when none is held.

Follow `tests/helpers/runtime_bootstrap.py` for FreeCAD-free collection —
these must run under plain CPython with no FreeCAD install.

### 7.2 Live — `tests/e2e/test_gui_lane_stays_unblocked.py` (new, marked `e2e`)

Prerequisite: the `--profile-name` override from §5.1.

Fixture builds a **fresh throwaway profile** (e.g. `.freecad-mcp-e2e-session/`,
port 9877), starts FreeCAD into it, yields, and tears it down. Then:

1. Establish a session; assert a GUI read and a document write both succeed.
2. Force expiry (inject a short TTL) and prune via a second handshake.
3. Assert the same GUI read and document write **still** succeed.
4. Assert the recovery is visible in `debug_logs/` (WI-4).

Follow `tests/e2e/_helpers.py` conventions — FreeCAD imported lazily inside
functions, collection gated with `pytest.importorskip`.

### 7.3 Soak — same file, opt-in via env flag, marked `e2e`

Alternate idle-past-TTL with GUI + write calls over N cycles (default 3, ~20 min)
against the throwaway instance; assert zero refusals. Concurrently run a second
MCP runtime that handshakes periodically, to exercise §4.3 continuously. **This is
the test that would have caught the reported degradation.**

---

## 8. Verification

Run from `tools/mcp/freecad-mcp` with `.venv-windows/Scripts/python.exe`.

1. `python -m pytest tests/test_session_recovery_contract.py tests/test_phase18_dispatch_session_elevation.py tests/test_json_rpc_client_transport.py -v`
2. WI-0's pre-fix reproduction (see WI-0 — a pass here pre-fix invalidates the diagnosis).
3. `python -m pytest tests -m unit` — no regressions across the 133 test modules.
4. `python -m pytest tests/e2e/test_gui_lane_stays_unblocked.py -m e2e -v`, then
   confirm teardown left nothing behind and that PID 8616 / `.freecad-mcp-isolated`
   are untouched (`get_instance_info` on 9876 should still report
   `addon_runtime_id: cee53853-a481-4066-aa1c-540c6ff7d89f`, pid 8616).
5. Soak, ≥3 TTL cycles, zero refusals.
6. FreeCAD: build and run the `App` test target for `DocumentCollaborationService`.
7. `python -m pytest tests/test_architecture_policy.py`, plus a generator re-run
   confirming the edited generated files produce a no-op diff (§5.2).

**Commit as two changes:** MCP submodule fix + tests first, then the FreeCAD-side
gtest together with the submodule gitlink bump.

---

## 9. Reference — evidence already gathered

So you don't repeat it. Captured 2026-08-09 against the live instance; both calls
are unauthenticated reads and mutate nothing.

```
POST http://127.0.0.1:9876/jsonrpc
  {"jsonrpc":"2.0","method":"ping","params":[],"id":"probe"}
  → {"jsonrpc":"2.0","id":"probe","result":true}

  {"jsonrpc":"2.0","method":"get_instance_info","params":[],"id":"probe"}
  → instance_id 0a991ef2-2bd7-4184-9e09-b1e98f0cad28
    addon_runtime_id cee53853-a481-4066-aa1c-540c6ff7d89f
    pid 8616, addon_loaded_at 2026-08-09T06:37:13Z
    addon_version 0.2.0, protocol_version 2, document_lease_mode enforce
    freecad 26.3.0 / 48091 (Git) / built from 45c3e616db

  {"jsonrpc":"2.0","method":"get_report_view","params":[],"id":"probe"}
  {"jsonrpc":"2.0","method":"get_gui_state","params":[],"id":"probe"}
  {"jsonrpc":"2.0","method":"get_selection","params":[],"id":"probe"}
  → all three: code -32000,
    "This operation requires a handshake_v2 session and an immutable
     authenticated request envelope",
    data.error_code = "LEASE_PROTOCOL_REQUIRED"
```

Read lane healthy; GUI lane gated exactly as designed; methods present (§5.4).
Header required on every request: `X-FreeCAD-MCP-Protocol: jsonrpc-2.0`.

### Key file map

| concern | path |
|---|---|
| the gate | `addon/.../dispatch_helpers_ops/dispatch_core_enforcement_auth.py:8,53` |
| GUI lane entry | `addon/.../dispatch_helpers_ops/dispatch_core.py:13-38` |
| write lane entry | `addon/.../v2_methods_ops/invoke_v2.py:18-117` |
| session invalidation | `addon/FreeCADMCP/_shared/protocol/session_manager.py:139-243` |
| TTL / limits | `addon/FreeCADMCP/_shared/protocol/constants.py:37-63` |
| error → wire shape | `addon/FreeCADMCP/_shared/protocol/public_error.py`, `protocol_error.py:34` |
| **the bug** | `src/freecad_mcp/generated/capabilities/connection_methods/connection_invoke_v2_helpers.py:16,161` |
| retry routing | `src/freecad_mcp/generated/capabilities/connection_methods/connection_invoke_v2_ops.py:63,87` |
| handshake / refresher install | `src/freecad_mcp/server_ops/manifest_auth.py:100-190` |
| client session custody | `src/freecad_mcp/rpc_session.py` |
| existing (insufficient) coverage | `tests/test_phase18_dispatch_session_elevation.py:81,108,128` |
| FreeCAD RecomputeFailed fixture | `tests/src/App/DocumentCollaborationService.cpp:1477` |
| C++ result struct | `src/App/DocumentCommitCoordinator.h:36-49` |
