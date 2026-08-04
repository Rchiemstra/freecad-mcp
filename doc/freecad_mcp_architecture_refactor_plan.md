# FreeCAD MCP architecture refactor plan

Plan to reshape `feature/dirty-document-adoption` into a **thin two-process
adapter**: an MCP server free to use any dependency, and an add-on that is a
pure-stdlib gateway inside FreeCAD. One protocol implementation, one wire
encoding, one place to declare a capability.

This plan starts after native Phases 1–6 of the repository-root
[`freecad_document_collaboration_plan.md`](../../../../doc/freecad_document_collaboration_plan.md)
are complete. The collaboration plan's former standalone Phase 7 is absorbed
here: this plan first reorganizes and routes the MCP adapter, then performs the
authoritative collaboration cutover in Phase 18. After that gate, FreeCAD alone
owns collaboration, document lifecycle, persistence, recovery, and conflict
decisions. No phase may extend the temporary Python lease authority while it is
being retired.

The completed [`module-size-refactor-plan.md`](module-size-refactor-plan.md) is
the structural baseline. Its thin façades, explicit exports, compatibility
shims, and contract snapshots are inputs. Its ARCH001/ARCH002 size rules are
**not** — this plan retires them in Stage 0, because they are what produced the
31 modules currently split by line count rather than by subject.

**In scope**

- `addon/FreeCADMCP/` gateway layering, runtime ownership, and startup/shutdown
- `src/freecad_mcp/` client, capability packages, and tool registration
- the wire encoding and the single shared protocol module
- capability manifests and generated registration
- `addon/FreeCADMCP/document_lease/` compatibility and deprecation surfaces
- architecture policy replacing the module-size rules

**Out of scope**

- Redesigning the native collaboration model delivered by Phases 1–6 of the prerequisite plan
- Reintroducing MCP-owned sidecars, heartbeats, credentials, document ownership,
  save/recovery authority, or FCStd-difference conflict policy
- Renaming public **MCP tool** names, parameters, descriptions, or result envelopes
- Collapsing the two processes into one (see §3.2 for why)
- Moving off loopback TCP to a permissioned socket (see §3.4 — separate spike)
- Removing compatibility import shims; that is a later deprecation plan

**Success criteria**

- Public MCP tool names, parameters, descriptions, registration order, and
  returned envelopes remain contract-identical.
- Native FreeCAD remains the only owner of collaboration sessions, lifecycle
  epochs, dirty/persisted state, save, Save As, recovery, and mutation authority.
- The add-on imports nothing outside the Python standard library and FreeCAD.
- Exactly one protocol implementation exists, vendored into both processes and
  gated by a byte-equality check.
- The wire is JSON-RPC 2.0 end to end; failures travel as errors, not as
  success-shaped envelopes.
- Each capability is declared in exactly one manifest entry; registration is
  generated and asserted byte-equal to the frozen registry snapshot.
- One bootstrap composition root owns the only mutable process runtime singleton.
- No application code performs a `_rpc_mod()` runtime lookup.
- Architecture policy measures capability ownership, dependency direction, public
  surface, and complexity — never physical line count.

---

## 1. Goals and non-goals

### Goals

- Make the add-on a gateway, not a second application.
- Remove the encoding mismatch between the MCP hop and the RPC hop.
- Delete the protocol twins rather than synchronizing them.
- Declare each capability once and generate the rest.
- Construct runtime services explicitly and dispose them deterministically.
- Preserve every public MCP contract and existing import shim throughout.
- Keep every phase commit coherent, testable, revertible, and working.

### Non-goals

- Designing a second collaboration or lease state machine in Python.
- Moving native lifecycle, persistence, recovery, or rollback policy back to MCP.
- Building a ports-and-adapters layer where there is no policy left to protect.
- Introducing a dependency-injection framework.
- Removing old import paths because in-tree callers have migrated.
- Splitting or merging files to satisfy a line-count target.

---

## 2. Hard constraints

| Constraint | Implication |
|------------|-------------|
| Native foundation first | No phase starts until native collaboration Phases 1–6 are complete and verified against the actual tree. The former Phase 7 is executed through this plan. |
| Native authority target | Only FreeCAD may authorize document mutation or decide lifecycle, save, recovery, persistence, and conflict outcomes after Phase 18. Until then, existing lease machinery is frozen compatibility debt: it may keep the branch working but may not be expanded or become a dependency of new code. |
| Add-on dependency purity | The add-on imports only the Python standard library and FreeCAD. A compiled or third-party dependency in the add-on is blocking. |
| Compatibility lease records | New decoder/shim surfaces may decode historic data but may not rotate authority, fence a live document, or advance native lifecycle state. Existing live records remain only as named Phase 18 allowances until their callers are routed. |
| Public MCP surface | Tool names, parameters, descriptions, registration order, returned envelopes, and exported tool objects remain frozen by the registry snapshot. |
| Semantic RPC contract | The RPC contract is frozen as method name → parameters → result schema, **independent of encoding**, so it validates both listeners during migration. |
| Import compatibility | Every moved symbol keeps an explicit re-export at its old path. Shim removal is outside this plan. |
| GUI-thread safety | FreeCAD and Qt work remains behind the GUI dispatcher; capability code never bypasses it. |
| Typed authorization target | New and migrated internal code receives immutable authorization evidence, never a new unrestricted `local_confirmation=True` boolean; existing boolean paths are named allowances until their owning routing phase removes them. |
| Layer direction | `transport` → `dispatch` → `capabilities` → FreeCAD. No layer imports upward; `runtime` constructs the graph and is imported by none of them. |
| Runtime ownership target | By Phase 17, mutable process-wide services and registries exist only inside `AddonRuntime`, with at most one bootstrap-owned reference. |
| Generated registration | Generated output is asserted byte-equal to the frozen registry snapshot. A hand edit to generated code is blocking. |
| Manifest ownership | One manifest file per capability subject. A single global manifest is blocking — it destroys exclusive worker ownership. |
| Atomic phase commits | Every phase commit includes its focused regressions, leaves the branch working, and can be reverted independently. No stage squash, merge, or validation-only commits. |
| Docker-only evidence | Host-side test runs do not count. All evidence is produced in Docker. |

Related design inputs:

- [`freecad_document_collaboration_plan.md`](../../../../doc/freecad_document_collaboration_plan.md)
- [`module-size-refactor-plan.md`](module-size-refactor-plan.md)
- [`document-leases.md`](document-leases.md), [`lease-recovery.md`](lease-recovery.md), [`lease-security.md`](lease-security.md)
- [`request-lifecycle.md`](request-lifecycle.md), [`runtime-identity.md`](runtime-identity.md), [`structured-results.md`](structured-results.md)

When an older lease document conflicts with the native collaboration model or the
Phase 18 cutover contract, the collaboration plan wins. Preserve the old public
result or return its frozen deprecation result; do not extend or restore the old
authority implementation.

---

## 3. Target architecture

### 3.1 Collaboration authority target

The completed native foundation changes what several MCP lease concepts mean.
This plan preserves their public compatibility while routing every ingress to the
native boundary, then removes their old authority in Phase 18.

| Legacy concept | Post-cutover owner | MCP responsibility |
|---|---|---|
| Lease owner, token, generation, heartbeat | Removed; native edit sessions and epochs replace it | Decode old payloads, redact secrets, return the frozen compatibility result |
| Dirty adoption and `LOCKED_ERROR` handoff | Native collaboration session APIs | Gather typed GUI evidence, translate request and result |
| Local and foreign orphan recovery | Native lifecycle and recovery APIs | Invoke or query native recovery, or return the documented deprecation result |
| Save, Save As, finalize, release | Native FreeCAD lifecycle | Route one typed request, translate the response |
| Sidecar state and FCStd baseline comparison | Removed from MCP correctness | Read old formats only where migration or deprecation requires it |
| Close/reopen, persisted marker, lifecycle epoch | Native FreeCAD | Expose read-only status |

Phase 18 must prove that an MCP restart, replacement, or authentication-session loss
does not transfer, revoke, or corrupt document authority. Compatibility shims cannot
make a native operation legal and cannot mutate native session state.

### 3.2 Two processes, three layers

The process split stays. Three properties pay for it:

1. **Crash isolation.** A failed adapter leaves the CAD session and its unsaved
   document intact.
2. **Dependency freedom.** The MCP process uses any Python and any dependency;
   the add-on stays stdlib-only, so nothing compiled must be installed into four
   different FreeCAD bundle formats.
3. **The isolation model.** Headless `FreeCADCmd` workers and multi-instance
   scenarios require the MCP process to be separable from any one FreeCAD.

Inside the add-on, three layers and one composition root:

```text
addon/FreeCADMCP/
  transport/        listener, authentication, replay          (no FreeCAD import)
  dispatch/         GUI-thread marshalling, cancellation,
                    inflight and continuation registries      (no FreeCAD import)
  capabilities/     one package per subject; thin typed calls (FreeCAD here only)
  runtime.py        the single composition root
  _shared/protocol/ vendored; identical to the client copy
```

`transport` and `dispatch` are FreeCAD-free and therefore genuinely unit-testable
without FreeCAD. That is where a port abstraction earns its keep. It is **not**
introduced anywhere else: after the cutover the policy lives in C++, so a handler
per lifecycle verb would wrap exactly one typed native call and add nothing.

```mermaid
flowchart TB
    Agent[AI agent]
    subgraph MCPProc[MCP server process]
        Man[capability manifests]
        Gen[generated registration]
        Caps[capabilities by subject]
        CT[client transport]
    end
    Shared[_shared/protocol - one module, vendored both sides]
    subgraph GW[Add-on gateway]
        GT[transport]
        GD[dispatch]
        GC[capabilities]
        RT[runtime.py composition root]
    end
    subgraph Core[FreeCAD core - sole authority]
        Facade[DocumentCollaborationService]
        Doc[App::Document]
    end
    Agent -->|MCP JSON-RPC 2.0| Gen
    Man --> Gen --> Caps --> CT
    CT -->|JSON-RPC 2.0, same framing| GT
    Shared -.-> CT
    Shared -.-> GT
    Man -.->|generates| GC
    GT --> GD --> GC --> Facade --> Doc
    RT -.-> GT
    RT -.-> GD
    RT -.-> GC
```

### 3.3 One protocol, one encoding

MCP **is** JSON-RPC 2.0. Today the client speaks JSON-RPC to the agent, re-encodes
to XML-RPC, and decodes back — an impedance mismatch between two halves of one
product. It has three concrete costs:

- **Errors.** XML-RPC gives `Fault(int, string)`. Anything richer must travel
  inside a *successful* response carrying a failure envelope. The collaboration
  design requires conflict results to return changed semantic keys with expected
  and current revisions (`freecad_document_collaboration_plan.md` §7); that maps
  onto `error.data` and nowhere good in XML-RPC.
- **Cancellation.** Advisory cancellation is fire-and-forget by nature. XML-RPC
  forces a full request/response cycle; JSON-RPC notifications do not.
- **Values.** XML-RPC has no `null` without a non-standard extension, and its
  standard integer is 32-bit signed — so the monotonic 64-bit revision counters
  must be smuggled as strings or doubles.

The two protocol implementations (`lease_protocol*` in the add-on, `rpc_auth*` in
the client) exist only because the boundary exists. Canonicalization, HMAC,
nonce, and bounds checking are pure stdlib. They become **one** module vendored
into both sides with a byte-equality check in CI. The existing conformance
vectors survive as ordinary tests of that module, not as a permanent
cross-process synchronization apparatus.

### 3.4 Encoding and channel are separate decisions

JSON-RPC 2.0 is the **encoding** and is platform-neutral; it proceeds in Stage 1.

Moving off loopback TCP to a permissioned channel — Unix domain socket or named
pipe — is the larger security win, because much of the signing layer exists to
defend a port reachable by any local process. It is **not** in this plan. CPython's
`AF_UNIX` support on Windows is patchy and the fallback is a named pipe or a token
file; that needs its own spike on the primary development platform. Stage 2 keeps
the listener swappable so the channel can change later without touching dispatch.

### 3.5 Capability manifests and generation

Every CAD capability currently lives in four hand-maintained places: the MCP tool
module, the client operation, the code template, and the add-on RPC method. That
is the cost worth removing, and the codebase already generates code — the
`templates/*.py.txt` files are generated FreeCAD scripts.

A capability is declared once, in a manifest owned by its subject:

```text
src/freecad_mcp/capabilities/<subject>/manifest.py
    name, description, parameter schema, result schema,
    execution mode (typed gateway call | generated script),
    GUI-thread requirement, mutation classification
```

The generator emits the MCP tool registration, the client call stub, and the
gateway dispatch entry. The manifest is **bootstrapped from** the existing frozen
registry snapshot, and generated output is then asserted byte-equal to it — a
mechanically stronger guarantee than review-verified relocation.

Generation must prove itself against the awkward subjects before the tree
commits: sketch constraints, FEM, and assembly joints. A subject that resists the
schema uses an escape hatch — the manifest entry points at a hand-written
implementation — but if all three need one, Stage 5 does not collapse as planned
and the phase list is revised under §5.5.

### 3.6 Moved-symbol compatibility

Every symbol moved by this plan remains importable from its old defining module.
Origin modules keep explicit re-exports and declare an explicit `__all__`; they do
not rebuild exports from `globals()`.

- Shims are import-only or documented deprecation adapters.
- Shims own no mutable state, registration, runtime lookup, authority, or policy.
- Internal modules import the defining module, never the old shim or a barrel.
- Module-to-package conversions retain the original path via `__init__.py`.
- A removed re-export is blocking and is restored in the same phase.
- Shim removal belongs to a later deprecation plan.

### 3.7 Architecture policy

ARCH001 (300 lines) and ARCH002 (one class per file) are retired in **Stage 0**,
not at the end. They are what produced `tools_sketch_curves_a2.py` and
`bind_part_2.py`; keeping them through the migration would distort every
intermediate state and force files to be moved twice. Their replacement lands in
the same phase:

- capability ownership — one subject per production module;
- layer direction — `transport` → `dispatch` → `capabilities`, never upward;
- no `_rpc_mod()` or equivalent runtime locator in any layer;
- no internal imports through package barrels;
- explicit, declarative, side-effect-free compatibility shims;
- public-symbol budget per package;
- per-function complexity, retaining Ruff `C901`; and
- a generous mixed-responsibility backstop so giant grab-bags still fail.

Cohesive modules holding several closely related value types are accepted. Giant
façades, mixed-capability grab-bags, and boundary-crossing imports fail.

---

## 4. Execution prerequisite and baseline

The authoring-time tree contains the completed native collaboration foundation and
the still-live pre-cutover lease machinery. Execution begins from that mixed
baseline, so **phase 1 refreshes this inventory before any implementation**. The
legacy authority paths remain frozen and explicitly allowed only until Phase 18.

### 4.1 What phase 1 must establish

1. **Recorded revisions.** Parent revision containing completed native Phase 6 and
   the MCP submodule revision selected as the refactor base.
2. **The planned compatibility manifest.** Every legacy lease path classified as
   temporary implementation, retained compatibility/deprecation shim, or planned
   removal. Phase 1 derives and commits this initial manifest as
   `tests/fixtures/post_collaboration_compatibility_surface.json`; Phase 18 updates
   it to the verified post-cutover state. The following are expected to survive as
   import, decoder, or deprecation shims — but the committed manifest, not this list,
   is authoritative:
   `src/freecad_mcp/lease_manager.py`, `document_lease/model.py`,
   `document_lease/types/transitions.py`, `document_lease/sidecar.py`,
   `document_lease/service.py`, `document_lease/service_ops/facade_bindings.py`,
   and the frozen public lease RPC adapters.
3. **Removal inventory.** Record every reachable `core_authority`,
   `claim_locked_error_handoff` owner rotation, lease observer, heartbeat, sidecar
   correctness path, and MCP save/recovery authority path. Each receives an explicit
   Phase 18 removal owner and a negative end-state assertion. New code may not call
   these paths.
4. **The locator census.** Per-module counts of `_rpc_mod()` and equivalent runtime
   lookups — 514 AST locator nodes at execution (10 definitions plus 504 syntactic
   references, of which 432 are runtime calls). Text-only comments/docstrings are
   excluded. Stage 3 is sized from this census and the final gate measures against it.
5. **The compose-lane decision.** `tools/mcp/freecad-mcp/Dockerfile` installs
   FreeCAD from conda-forge, so the `core`, `e2e`, and `benchmark` services run
   against a build with **no native collaboration bindings**. Phase 1 records one of:
   (a) the compose image is rebased onto the Docker branch build, or (b) those
   services are scoped as adapter-only evidence and every phase touching a
   collaboration path additionally runs the branch-built cross-track lane. Deciding
   this at phase 1 rather than discovering it mid-stage is mandatory.
6. **The semantic contract snapshot.** `freecad_rpc_contract_snapshot.json` is
   rewritten as method → parameters → result schema, independent of encoding, so it
   validates both listeners during Stage 1.

If the actual native foundation or pre-cutover MCP tree contradicts the derived
manifest in a way that removes a phase's subject entirely, phase 1 **re-scopes the
phase list** under §5.5 and records the change. Stopping the program is reserved
for a contradiction that cannot be resolved by re-scoping.

### 4.2 Current seams

| Current area | Current pattern | Required end state |
|---|---|---|
| `rpc_server/rpc_server.py`, `rpc_server_ops/facade_bindings.py` | Transport façade, runtime globals, private helpers, and dynamically attached operations in one module | `transport/` plus a bootstrap-owned runtime |
| `rpc_server/methods/*_ops/` | Application paths locate `rpc_server` through `_rpc_mod()` and pass authorization booleans | `capabilities/` with constructor-injected collaborators and typed evidence |
| `rpc_server/server_lifecycle.py`, `server_shutdown.py`, `InitGui.py` | Startup and shutdown coordinate scattered module state | Construct and dispose one `AddonRuntime` |
| addon `lease_protocol*`, client `rpc_auth*` | Two compatible implementations | One vendored `_shared/protocol/`, byte-equality gated |
| `document_lease/service.py`, `service_ops/facade_bindings.py` | Methods attached after class definition | Thin façade delegating to capabilities |
| `lease_manager_ops/lease_client_manager*.py` | Class body assembled from binding modules | Normal class; old modules import-only shims |
| `tools_*_a.py`, `_b.py`, `_1.py`, `_2.py` (31 modules) | Ownership follows split suffixes | Subject packages generated from manifests; old paths declarative shims |
| `server_ops/tool_registration.py`, `tools_register_order.py`, `tool_exports/bind_part_*.py` | Registration mutates imported modules; order is a hand-written list | Typed `ToolDependencies`; generated ordered registration |
| `ci/lint_python.py` | ARCH001/ARCH002 enforce size and one-class rules | Capability, dependency, shim, surface, and complexity rules |

---

## 5. Multitask operating model

### 5.1 Roles

This plan adopts the prerequisite's Codex subagent policy
(`freecad_document_collaboration_plan.md` §5.1–§5.2). The earlier Composer/Cursor
policy in this document is superseded; the two plans run in one program and must
not use divergent worker policies.

| Role | Model and reasoning | Responsibilities |
|---|---|---|
| **Worker** | **GPT-5.6 Terra / high** by default; **GPT-5.6 Sol / high or xhigh** for the risk classes below | Implements one frozen workstream under exclusive file ownership. Does not edit shared files. Adds focused tests. |
| **Integrator** (parent) | Session parent model; raise effort for shared-seam integration | Partitions work, freezes interfaces, owns shared files, waits for every worker in a wave, combines outputs, runs every Docker suite, updates §11, creates the single phase commit. |
| **Reviewer** (read-only) | **GPT-5.6 Sol / xhigh**; **max** only for an unresolved correctness blocker | Reviews adversarially after every workstream and after integration. Reports blocking, important, and non-blocking findings. Never edits. |

Risk classes requiring Sol: the wire migration and error-model change, the shared
protocol module, runtime construction and disposal, cancellation and GUI-thread
seams, the generator's contract-equality proof, and every review gate.

### 5.2 Hard rules

1. Apply the prerequisite's §5.2.1 test before every spawn; record task, done
   condition, model, reasoning level, exclusive paths, and dependencies.
2. Do not delegate a whole phase to one worker when at least two safe workstreams
   exist; do not split a tightly coupled workstream to manufacture parallelism.
3. Assign exclusive file ownership before starting a wave.
4. Workers never edit §5.3 shared files.
5. Workers do not recursively delegate without explicit integrator authorization.
6. Workers report changed files, tests, assumptions, and blockers (§5.6).
7. One integrator owns shared files, integration, Docker execution, §11 updates,
   and the single phase commit.
8. The integrator waits for all workers in a wave before combining.
9. After every workstream, run a read-only **Sol / xhigh** review of the actual diff.
10. Fix every blocking and important finding, then re-review.
11. Run the required Docker suites before the phase commit (§5.7).
12. Do not mark a phase complete unless all reviews and suites pass.
13. If fewer than two independent workstreams remain, use one worker or work
    locally and record why.
14. One commit per phase, inside `tools/mcp/freecad-mcp`.
15. Every moved symbol keeps its old import path (§3.6); a removed re-export is blocking.
16. Verify assigned models before each wave; never silently downgrade.
17. Keep one runtime slot free for the integrator.

### 5.3 Shared files (integrator-only)

- `doc/freecad_mcp_architecture_refactor_plan.md`
- `ci/lint_python.py`, `tests/test_architecture_policy.py`
- `tests/fixtures/freecad_rpc_contract_snapshot.json`
- `tests/fixtures/mcp_tool_registry_contract_snapshot.json`
- `tests/fixtures/post_collaboration_compatibility_surface.json`
- `addon/FreeCADMCP/_shared/protocol/` and `src/freecad_mcp/_shared/protocol/`
- `addon/FreeCADMCP/runtime.py`, `rpc_server/rpc_server.py`,
  `rpc_server/server_lifecycle.py`, `rpc_server/server_shutdown.py`, `InitGui.py`
- `addon/FreeCADMCP/document_lease/__init__.py`; `document_lease/service.py` during façade reduction
- `src/freecad_mcp/server.py`, `tools_register_order.py`,
  `server_ops/tool_registration.py`, `server_ops/tool_exports/`
- the manifest **schema** and the generator; individual subject manifests are worker-owned
- central `__init__.py` and `__all__` composition files
- `Dockerfile`, `docker-compose.yml`, and the parent-repository gitlink
- for Phase 18, the parent plan, App/Gui authority sources and build registration,
  `src/Gui/Command.cpp`, `src/Gui/Dialogs/DlgMutationTakeover.*`,
  `tests/src/App/DocumentMutationAuthority.cpp`, and
  `tests/src/Gui/CollaborationAuthorityRemoval.cpp`
- for Phase 12, `src/App/Document.pyi`, `src/App/DocumentPyImp.cpp`, the focused
  native compatibility-binding test and its test CMake registration, the parent
  plan, and the parent gitlink

### 5.4 Cross-repository delivery

Except for Phases 12 and 18, substantive phase commits are created inside
`tools/mcp/freecad-mcp`. The parent gitlink is **not** frozen for the whole program:
the branch-built cross-track lane builds the parent branch at its recorded submodule
revision, so a frozen gitlink would test the pre-refactor add-on at every gate. The
integrator bumps the parent gitlink in a separate parent commit at each integration
gate (phases 1, 3, 5, 12, 18, 19, 22, and 23), or records that the lane mounts the
submodule worktree at its actual HEAD. Either is acceptable; leaving the gitlink
stale through the program is not.

Phase 12 is one logical cross-repository integration delivery with two Git objects:
one nested MCP phase commit and one canonical parent commit containing the minimal
native Python compatibility-mutation binding and tests, the updated gitlink, and both
plan/progress updates. The binding exposes only a synchronous UnknownModel mutation
over FreeCAD's existing `DocumentCollaborationService::commitCompatibilityMutation`;
it accepts no caller-supplied stable identity, owner, token, generation, confirmation
boolean, or TLS/capability grant. It must enter through the GUI dispatcher, manage the
GIL without deadlock, propagate Python exceptions into native rollback, and return the
native structured result. The revision-neutral `serializeCompatibilityCallback` is not
exposed as a generic remote mutation surface.

Phase 18 is one logical cross-repository cutover with two unavoidable Git objects:
one squashed nested MCP commit and one parent commit containing the native authority
removal, the updated gitlink, both plan/progress updates, and the final cross-track
evidence. The parent commit is the canonical Phase 18 delivery. Worker commits are
never delivery units.

### 5.5 Re-scoping authority

Phase 1 alone may revise the phase list, and only from verified facts about the
native Phase 6 parent and pre-cutover MCP tree — a phase whose subject no longer
exists is deleted, and phases whose subjects merged become one. Every change is
recorded in §11.3 with its justification. After phase 1, the list is fixed; a later
discovery that invalidates a phase blocks under §7 rather than silently re-planning.

### 5.6 Worker report template

```text
## Workstream <id> report
- Phase commit: <number and exact subject>
- Changed paths: <exclusive files>
- Behavior preserved: <contracts and shims>
- Tests added or updated: <paths and cases>
- Docker validation: <commands and results>
- Assumptions or blockers: <none or explicit list>
```

### 5.7 Docker gates

**Every phase**

- affected unit tests, relevant contract fixtures, Ruff on touched files, and
  architecture lint when a boundary or package layout changes; plus
- the `unit` Compose service; plus
- the branch-built cross-track lane for any phase touching a collaboration path,
  per the phase-1 compose-lane decision (§4.1 item 5).

**Integration gates — phases 1, 3, 5, 12, 18, 19, 22, and 23**

- all four Compose services: `unit`, `e2e`, `core`, `benchmark`;
- architecture lint and full Ruff;
- registry, semantic RPC, import/deprecation, and protocol contract fixtures; and
- the branch-built FreeCAD and MCP cross-track lane.

The per-phase gate deliberately does not run all four services. The registry and
semantic contract snapshots are what protect the public surface, and they are cheap;
running `benchmark` after every file move buys nothing. The integrator records the
Docker image/digest, commands, counts, and results in §11. Host-side runs are ignored.

---

## 6. Ordered implementation

```text
Stage 0  Baseline, policy, and one protocol      phases 1–3
Stage 1  Wire migration to JSON-RPC 2.0          phases 4–5
Stage 2  Compatibility surfaces                  phases 6–7
Stage 3  Gateway layers                          phases 8–11
Stage 4  Locator removal and bootstrap           phases 12–17
Stage 5  Collaboration cutover                   phase 18
Stage 6  Typed registration                      phase 19
Stage 7  Manifests and generation                phases 20–22
Stage 8  Final enforcement                       phase 23
```

Phase numbers are continuous and authoritative. A later stage never starts before
all earlier phases and their marked gates are complete.

### Stage 0 — Baseline, policy, and one protocol

**Outcome:** the completed native foundation and temporary pre-cutover MCP state are
recorded as the execution baseline; the distorting size rules are gone before any
code moves; the protocol exists once.

| # | Phase commit | Change and main paths | Focused tests and validation |
|---:|---|---|---|
| 1 | `test(mcp): freeze the native collaboration baseline` | All six items in §4.1: revisions, planned compatibility manifest, removal inventory, locator census, compose-lane decision, and semantic contract snapshot. Refresh the MCP registry snapshot and record every temporary authority allowance without changing runtime behavior. | Import/deprecation, collaboration-boundary, semantic RPC, MCP registry, restart, legacy-authority census, and native-API availability contracts; **integration gate**. |
| 2 | `build(mcp): replace module size rules with boundary policy` | Retire ARCH001/ARCH002 from `ci/lint_python.py`; add capability ownership, layer direction, locator ban, barrel-import ban, shim purity, public-surface budget, and the mixed-responsibility backstop, each with named structural allowances recorded exactly. Phase 1 separately owns temporary authority allowances. Retain Ruff `C901`. | `tests/test_architecture_policy.py`; accept cohesive multi-class value modules; reject giant façades and grab-bags; architecture-only lint. |
| 3 | `refactor(mcp): extract the shared protocol module` | Create `_shared/protocol/` with canonicalization, signing, nonce, replay, and bounds checking; vendor identically into both processes; add the byte-equality CI check. `lease_protocol*` and `rpc_auth*` become import shims. Framing is still XML-RPC. | Existing protocol and auth suites become tests of the one module; byte-equality gate; both façades unchanged; **integration gate**. |

Phase 2 lands before any code moves, deliberately. Keeping a 300-line rule through
a migration forces files into shapes that must be undone later.

### Stage 1 — Wire migration

**Outcome:** JSON-RPC 2.0 end to end; failures are errors.

| # | Phase commit | Change and main paths | Focused tests and validation |
|---:|---|---|---|
| 4 | `feat(mcp): add the JSON-RPC 2.0 transport` | Add JSON-RPC 2.0 framing to `_shared/protocol/`; bind the new listener **alongside** XML-RPC onto the same dispatch path; define the structured error model mapping conflict, stale, cancellation, and lifecycle results onto `error.code/message/data`. | Both listeners satisfy the semantic contract; error-model mapping; batch; notification; `null` and 64-bit integer round-trips; replay and signing across both framings. |
| 5 | `refactor(mcp): migrate to JSON-RPC and retire XML-RPC` | Switch the client to JSON-RPC; convert success-shaped failure envelopes to native errors; add protocol-version negotiation with a clear mismatch error; remove the XML-RPC listener and leave a documented deprecation response. | Full semantic contract on the surviving listener; envelope-to-error conversion for every documented result; version-mismatch behavior; cancellation as notification; **integration gate**. |

Phase 4 leaves both listeners working, so phase 5 is independently revertible. The
error-model change lands here, before the generator exists, so the manifest's result
schema is designed against a native error model rather than inheriting the workaround.

### Stage 2 — Compatibility surfaces

**Outcome:** import-time class assembly is gone; native-session and historic-decoder
boundaries are explicit. Temporary live legacy behavior remains only behind named
Phase 18 allowances until the native routing phases replace it.

| # | Phase commit | Change and main paths | Focused tests and validation |
|---:|---|---|---|
| 6 | `refactor(mcp): define LeaseClientManager normally` | Move construction and methods into `lease_manager_ops/lease_client_manager.py`; binding and init modules become shims; introduce opaque native-session handles and compatibility results. Existing credential, heartbeat, and revocation behavior may remain only behind named Phase 18 allowances until phases 12–13 replace its live callers. | Construction, opaque handles, aliases, reconnect, redaction, public imports, no import-time binding, and no new legacy-authority dependency. |
| 7 | `refactor(mcp): isolate legacy lease decoders` | Separate immutable historic decoding in `model.py`, transition tables, and `sidecar.py` from the still-live legacy implementation. Decoder APIs cannot transition authority; all remaining mutable callers are enumerated as Phase 18 removals and otherwise left behaviorally unchanged until native routing is live. | Historic round-trip, malformed payloads, redaction, decoder immutability, forbidden decoder transitions, complete mutable-caller census, and unchanged temporary runtime behavior. |

**Parallelization:** two disjoint workers — 6 owns client paths, 7 owns add-on
`document_lease/` paths. They land in order.

### Stage 3 — Gateway layers

**Outcome:** the add-on has three layers and one composition root.

| # | Phase commit | Change and main paths | Focused tests and validation |
|---:|---|---|---|
| 8 | `refactor(mcp): introduce the gateway runtime` | Add `runtime.py` owning listener, dispatcher, workers, auth, replay, inflight and continuation registries, collaboration bridge, and shutdown state. It owns no document authority, dirty state, persistence, recovery policy, or sidecar store. | Pure construction, dependency identity, optional resources, ownership, and double-disposal — all without importing FreeCAD or Qt. |
| 9 | `refactor(mcp): establish the transport layer` | Move listener, authentication, and replay into `transport/`, consuming `_shared/protocol/`; keep the listener swappable so §3.4's channel change stays possible. | Bind, auth, replay, redaction, malformed framing, listener substitution, and no FreeCAD import from `transport/`. |
| 10 | `refactor(mcp): establish the dispatch layer` | Move GUI-thread marshalling, cancellation, and the inflight/continuation registries into `dispatch/`. | GUI-thread enforcement, cancellation, continuation bounds, timeout, concurrency, and no FreeCAD import from `dispatch/`. |
| 11 | `refactor(mcp): add the composition root` | Construct transport, dispatch, capabilities, auth, and the collaboration bridge in dependency order; existing startup calls this factory through a transitional hook before any locator is removed. | Authentication requirements, dependency sharing, transitional live-start wiring, forbidden authority dependencies, and rollback on construction failure. |

Phase 8 defines the container without starting it; phase 11 wires real adapters
through the existing startup path, so Stage 4 replaces locators without creating an
unused parallel graph.

### Stage 4 — Locator removal and bootstrap

**Outcome:** no runtime locator remains; startup and shutdown are deterministic.

Sized from the phase-1 census (514 sites at authoring time). Each phase reduces the
census measurably and records the remaining count.

| # | Phase commit | Change and main paths | Focused tests and validation |
|---:|---|---|---|
| 12 | `refactor(mcp): inject collaboration collaborators` | First expose a synchronous UnknownModel-only Python binding over FreeCAD's existing compatibility commit boundary, with no legacy authority dependency or caller-supplied identity; add the thin `collaboration_client.py` and add-on `collaboration_api.py` bridge over the frozen native API; pass acquisition, adoption, handoff, recovery, and compatibility-mutation collaborators into `methods/lease_methods_ops/`; remove their `_rpc_mod()` lookups. This is a two-object cross-repository delivery under §5.4. | Public compatibility shims, method/stub availability, exact-once callback, GUI-owner thread and off-thread GIL dispatch, UnknownModel wildcard publication, structured native results, Python exception rollback, lifecycle/reentrancy rejection, callback release, reconnect, adoption, recovery, authorization, cancellation, continuation, timeout, dependency identity, and no client/TLS/capability authority tests; **integration gate**. |
| 13 | `refactor(mcp): inject lifecycle collaborators` | Pass save, Save As, finalize, release, query, and deprecation collaborators into lease and lifecycle adapters; route them to native lifecycle results without MCP dirty, persistence, or recovery decisions. | Save, release, query, close/reopen, restart, cancellation, GUI dispatch, semantic RPC contract, and no-MCP-lifecycle-authority tests. |
| 14 | `refactor(mcp): inject execution collaborators` | Replace `_rpc_mod()` in dispatch, execute-code, and worker orchestration with injected dispatcher, execution-safety, worker, cancellation, and native compatibility-mutation dependencies. | Dispatch, execute-code, native mutation attribution, worker, cancellation, and AST no-locator scan. |
| 15 | `refactor(mcp): inject CAD collaborators` | Pass document, object, sketch, feature, transaction, and native collaboration/compatibility-commit collaborators into CAD adapters; remove their dependence on MCP mutation ownership. | CAD, object, sketch, feature, transaction, remote revision-stream publication, dependency identity, and AST no-locator scan. |
| 16 | `refactor(mcp): inject GUI and view collaborators` | Pass GUI dispatch, personal-view, presentation, snapshot, and restore collaborators into GUI and view adapters; add `collaboration_context.py` and route focus, screenshot, and refresh through the native personal-context API rather than authoritative global selection or active-view state. | GUI dispatch, camera/view, selection isolation, snapshot/restore, personal-context apply/render/restore, cancellation, and AST no-locator scan. |
| 17 | `refactor(mcp): bootstrap startup and shutdown through the runtime` | `start_rpc_server()` adopts the factory as its only path and publishes the singleton only after success; `stop_rpc_server()` cancels, stops, disposes, unsubscribes, drops adapter authentication/session handles, and clears idempotently without changing native document authority; `InitGui.py` routes manual start, auto-start, and about-to-quit through the root. | Repeated start, failed bind/auth/worker/bridge construction, reverse-order rollback, concurrent stop, inflight cancellation, native-session survival, partial runtime, repeated disposal, `InitGui` callback order, and no duplicate runtime. |

Phases 12–16 may be prepared in parallel where source and test ownership is disjoint;
workers add constructor parameters, the integrator edits central assembly. Phase 17 is
sequential and integrator-owned.

### Stage 5 — Collaboration cutover

**Outcome:** every remote mutation, lifecycle, recovery, and view operation uses the
native FreeCAD boundary; the temporary Python and native authority surfaces are gone.

| # | Phase commit | Change and main paths | Focused tests and validation |
|---:|---|---|---|
| 18 | `refactor(collaboration): cut over native MCP authority` | Remove live MCP lease ownership, heartbeat, sidecar-correctness, observer, FCStd-difference conflict, and save/recovery authority while retaining only the frozen decoder/deprecation shims. Remove the parent-tree `DocumentMutationAuthority`, `MutationCapability`, `MutationOwner`/`MutationOrigin`, `MutationAuthorityTLS`/`MutationInternalScope`, `DocumentPy` ownership methods, `AlterDoc` authority gate, and `DlgMutationTakeover` surface. Update package exports, CMake registration, the compatibility manifest, and both progress plans. | Remote operations enter the native revision stream; restart preserves document/lifecycle/persisted/recovery state; personal contexts are preserved; every old import returns its frozen shim or deprecation result; `CollaborationAuthorityRemoval.cpp` and negative reachability scans pass; branch-built App/Gui/Part tests, all four Compose services, and the branch cross-track lane pass; **integration gate**. |

Phase 18 starts only after phases 12–17 prove that every affected ingress and the
only startup path use injected native collaborators. Removal and façade rewiring are
integrator-owned because they cross the parent/submodule boundary. The compatibility
manifest changes from a planned classification to the verified post-cutover surface
in the same delivery. The cross-repository commit protocol in §5.4 is mandatory.

### Stage 6 — Typed registration

| # | Phase commit | Change and main paths | Focused tests and validation |
|---:|---|---|---|
| 19 | `refactor(mcp): pass a typed tool registration context` | Add `ToolDependencies` for server state, connection, recovery compatibility, collaboration, and selector; stop mutating imported tool modules in `server_ops/tool_registration.py`. | Simultaneous registration, dependency identity, selector isolation, deterministic order, no module mutation, server lifespan, registry snapshot; **integration gate**. |

This is the precondition for generation: a generated registrar must receive its
dependencies rather than reach for module globals.

### Stage 7 — Manifests and generation

**Outcome:** each capability is declared once; registration is generated and proven
equal to the frozen snapshot.

| # | Phase commit | Change and main paths | Focused tests and validation |
|---:|---|---|---|
| 20 | `feat(mcp): add capability manifests and the generator` | Define the manifest schema and the generator; bootstrap manifests for every subject from the frozen registry snapshot; emit registration, client stubs, and gateway dispatch entries into a shadow location. Prove the schema against sketch constraints, FEM, and assembly joints first. | Generated output byte-equal to the registry snapshot; schema coverage for the three awkward subjects; escape-hatch behavior; no hand edit to generated files. |
| 21 | `refactor(mcp): switch registration to generated output` | Replace `tools_register_order.py` and `server_ops/tool_exports/bind_part_*.py` with generated ordered registration; old modules become declarative shims. | Registration order, public server API, duplicate/missing exports, registry snapshot, and all old binder imports. |
| 22 | `refactor(mcp): delete the hand-written capability mirrors` | Remove the 31 mechanically split modules and the duplicated client operations and gateway methods now emitted by the generator; every old path remains an explicit shim. | Full registry snapshot, semantic RPC contract, generated FreeCAD code, per-subject behavior suites, and every old import path; **integration gate**. |

**Parallelization:** phase 20 is integrator-owned. In phases 21–22, disjoint workers
may migrate separate subjects concurrently; the integrator lands them in one commit
per phase and owns the generator, schema, and snapshots.

### Stage 8 — Final enforcement

| # | Phase commit | Change and main paths | Focused tests and validation |
|---:|---|---|---|
| 23 | `build(mcp): enforce the final architecture policy` | Remove every named structural allowance from phase 2; confirm Phase 18 removed every authority allowance; enforce add-on dependency purity, layer direction, zero locators against the phase-1 census, generated-registration equality, shim purity, and manifest-per-subject ownership. | Negative fixtures for each rule; full contract set; final **integration gate**. |

---

## 7. Verification checklist

### Every phase

- [ ] The exact next phase number and subject from §6 are used.
- [ ] The branch works before and after; the diff is independently revertible.
- [ ] Focused regressions land in the same commit as what they protect.
- [ ] Workers touched only exclusive paths; shared files were integrator-owned.
- [ ] Blocking and important review findings are cleared and re-reviewed.
- [ ] Public MCP names, parameters, order, envelopes, and old imports are unchanged
      or match the frozen deprecation contract.
- [ ] Every moved symbol has an explicit old-path shim with no import-time side effect.
- [ ] The add-on imports nothing outside the standard library and FreeCAD.
- [ ] `transport/` and `dispatch/` import no FreeCAD or Qt module.
- [ ] No new or migrated Python path creates document authority, lifecycle
      transitions, dirty state, sidecar correctness, or recovery policy; before
      Phase 18, every remaining legacy path is a named allowance from Phase 1.
- [ ] GUI work enters through the dispatcher; cancellation, replay, redaction, and
      authentication guarantees are intact.
- [ ] Required Docker suites pass per §5.7; Ruff passes on touched files.
- [ ] §11 is updated inside the substantive commit.

### At phase 1

- [ ] Native collaboration Phases 1–6 are complete at the recorded parent revision,
      and the selected MCP base revision is recorded.
- [ ] The planned compatibility manifest and complete Phase 18 removal inventory are committed.
- [ ] The locator census is recorded per module.
- [ ] The compose-lane decision is recorded and its consequences applied to §5.7.
- [ ] The contract snapshot is semantic, not encoding-bound.
- [ ] Any re-scoping under §5.5 is recorded with justification.

### At phase 5

- [ ] One listener remains and satisfies the full semantic contract.
- [ ] Every documented failure result travels as a JSON-RPC error, not as a success.
- [ ] Version mismatch produces a clear, documented error.
- [ ] 64-bit counters and `null` round-trip without smuggling.

### At phase 12

- [ ] The locator census has fallen measurably and the remaining count is recorded.

### At phase 19

- [ ] The locator census has fallen measurably and the remaining count is recorded.
- [ ] Tool registration receives typed dependencies and mutates no imported module.

### At phase 18

- [ ] Every remote mutation, lifecycle, recovery, save, and view ingress uses the native boundary.
- [ ] The final compatibility manifest matches the verified post-cutover tree.
- [ ] No live lease owner, heartbeat, sidecar correctness, observer, MCP save/recovery authority,
      `McpOwned`, `MutationAuthorityTLS`, `MutationInternalScope`, `AlterDoc` gate, or takeover dialog remains reachable.
- [ ] Restart, revision-stream, lifecycle/persistence/recovery, personal-context,
      import/deprecation, all-Compose, branch-built FreeCAD, and cross-track tests pass.

### At phase 22 and 23

- [ ] Generated registration is byte-equal to the frozen registry snapshot.
- [ ] Every capability has exactly one manifest entry and one subject owner.
- [ ] The locator census is zero.
- [ ] No structural allowance from phase 2 or authority allowance from phase 1 remains.
- [ ] Every old import path resolves; every shim is declarative.
- [ ] Architecture lint, Ruff, all four Compose services, contract fixtures, and the
      branch cross-track lane pass.

---

## 8. Commit sizing

| Delivery unit | Guidance |
|---|---|
| Invariant fix | One behavior correction plus focused regressions |
| Layer establishment | One layer, its tests, and its old-path shims |
| Locator slice | One adapter family; record the census delta |
| Wire slice | One listener addition or one retirement, never both |
| Capability migration | One subject per commit, including old-path shims |
| Contract fixture | Same commit as the surface freeze, or immediately before the protected move |
| Architecture gate | Substantive rule or allowance removal |
| Phase merge or squash | Forbidden |
| Validation-only commit | Forbidden |

Split when behavior, ownership, reviewability, or independent rollback provides a
real boundary — never to satisfy a line budget.

---

## 9. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Native foundation or MCP base differs from this plan | Phase 1 derives the manifest from the real tree and may re-scope under §5.5 rather than improvising or stopping. |
| The former collaboration Phase 7 published no compatibility manifest | Phase 1 derives and commits the planned manifest; Phase 18 verifies and updates it to the final state. |
| Compose services cannot exercise the native API | Phase-1 compose-lane decision; collaboration-touching phases run the branch-built lane. |
| Temporary lease authority is expanded before cutover | Phase-1 named allowances, no-new-dependency checks, native routing phases, and Phase-18 negative reachability tests. |
| Wire migration breaks an unknown external caller | Confirm before phase 4 whether anything outside this repo calls the RPC surface; dual-bind keeps both listeners live through phase 4. |
| Error-model change loses a documented result | The semantic contract enumerates every result; phase 5 maps each one explicitly and tests the conversion. |
| Generation cannot express a subject | Phase 20 proves the schema against sketch constraints, FEM, and assembly joints **first**; escape hatches are allowed and counted. |
| The manifest becomes a shared file | One manifest per subject is a hard constraint; a global manifest is blocking. |
| Generated code is hand-edited | Byte-equality assertion plus an architecture rule; a hand edit fails the gate. |
| Vendored protocol copies drift | Byte-equality check in CI, not review discipline. |
| Retiring size rules early lets grab-bags return | Phase 2 lands the replacement policy in the same commit, including the mixed-responsibility backstop. |
| Compatibility imports disappear during moves | Committed shim manifest, explicit re-exports, import tests, blocking review policy. |
| Circular imports after package moves | Leaf modules import defining modules, never barrels; restructure edges rather than adding lazy imports. |
| Runtime resources leak or a second singleton appears | Construction rollback, disposal-order tests, singleton policy, architecture fixtures. |
| Parent gitlink goes stale and the cross-track lane tests old code | §5.4 requires a gitlink bump at every integration gate, or a worktree-mounted lane. |
| Parallel workers edit shared façades | Exclusive paths; integrator-only façades, barrels, registries, fixtures, generator, and composition root. |

---

## 10. Command reference

Run all MCP commands from `tools/mcp/freecad-mcp`.

```powershell
# Architecture rules only
docker run --rm -v "${PWD}:/workspace" -w /workspace `
  ghcr.io/astral-sh/uv:python3.12-bookworm-slim `
  uv run ci/lint_python.py --architecture-only addon/FreeCADMCP src/freecad_mcp

# Full package lint and Ruff
docker run --rm -v "${PWD}:/workspace" -w /workspace `
  ghcr.io/astral-sh/uv:python3.12-bookworm-slim `
  uv run ci/lint_python.py addon/FreeCADMCP src/freecad_mcp

# Per-phase gate
docker compose run --rm unit

# Integration gate
docker compose run --rm unit
docker compose run --rm e2e
docker compose run --rm core
docker compose run --rm benchmark
```

Integration gates also run the Docker branch-build lane recorded from the native foundation:
current-branch FreeCAD App/Gui/Part tests plus the `.woodpecker/ci.yml` equivalents of
`freecad-mcp-load-preflight`, `freecad-mcp-core-tests`, and `freecad-mcp-e2e` against
the branch-built `FreeCADCmd`. Record the frozen image, configure/build commands, and
job commands in §11 before phase 1. Do not substitute a host build.

---

## 11. Progress

### 11.1 Snapshot

| Field | Current value |
|---|---|
| Authoring parent checkout | `feature/assembly-interference-detection`; Phase 1 execution base `863535a2d4b6c33b5bfce8171762320060a34afb` |
| MCP authoring branch | `feature/dirty-document-adoption`; Phase 1 execution base `5357d0c16a64b4981a5f508bc83dd07ddf4f1ca6` |
| Module-size baseline | Complete at `fc3a5236`; its size rules are retired by phase 2 |
| Collaboration prerequisite | Native Phases 1–6 complete; former Phase 7 absorbed into this plan as Phase 18 cutover |
| Execution parent revision | `6cbd05adfce1240339fe74b850c2ec96bbdf27ab` |
| Execution MCP base revision | `83fbe01e41690399acf1544e4e637e75fe06d988` |
| Current stage / phase | Stage 2 complete; Phase 7 complete |
| Next phase | 8 — `refactor(mcp): introduce the gateway runtime` |
| In-flight ownership | None |
| Last review | Phase 7 model/census, sidecar, and final integrated reviews clear on 2026-08-04 |
| Blocker | None; preserve the existing RPC surface as an externally consumed public contract |
| Resume hint | Phase 7 is committed and gated; begin Stage 3 with Phase 8 only, preserving the explicit historic decoder boundary and frozen Stage 1 wire contracts |

### 11.2 Stage status

| Stage | Phases | Integration gate | Status |
|---:|---|---|---|
| 0 | 1–3 | phases 1 and 3 | complete |
| 1 | 4–5 | phase 5 | complete |
| 2 | 6–7 | none | complete |
| 3 | 8–11 | none | pending |
| 4 | 12–17 | phase 12 | pending |
| 5 | 18 | phase 18 | pending |
| 6 | 19 | phase 19 | pending |
| 7 | 20–22 | phase 22 | pending |
| 8 | 23 | phase 23 | pending |

### 11.3 Progress log

Append entries newest-first. Each must be sufficient to resume without prior context.

#### 2026-08-04 — Phase 7 complete: legacy lease decoders isolated

- **Phase delivery:** `HistoricLeaseRecord` is a frozen, slotted, repr-redacted
  compatibility value with only fresh-copy `to_sidecar_dict()` and redacted
  `to_public_dict()` projections. `decode_historic_lease_record()` applies the
  complete existing schema without constructing `LeaseRecord` or exposing
  transition, revision, store, credential, or authority behavior. Direct
  construction is rejected. `decode_historic_sidecar_bytes()` is explicitly
  exported from both add-on and installed `document_lease.sidecar` spellings and
  applies the existing byte, UTF-8, JSON, and schema bounds.
- **Immutability, redaction, and malformed data:** historic payloads are copied
  recursively into read-only storage and every returned projection is independent.
  Credential and diagnostic fields, the complete structured error, and
  secret-bearing scalar values are removed or redacted. Malformed schema values,
  untrusted JSON, non-UTF-8 input, oversized input, and bounded deeply nested JSON
  become generic public errors with no retained cause, context, traceback payload,
  or input echo. `ALLOWED_TRANSITIONS` is now a read-only mapping over the existing
  frozenset edges; live transition validation is unchanged.
- **Compatibility and temporary runtime:** the existing `LeaseRecord`,
  `validate_transition`, `parse_sidecar_bytes`, and `SidecarStore` signatures,
  exports, and live behavior remain unchanged under their Phase 18 allowance. The
  compatibility manifest now names the historic model and byte decoder symbols.
  A separate exact Phase 18 census owns all 72 remaining mutable callers:
  11 revisions, 33 transitions, four store creates, seven store deletes, 13 store
  replacements, one call to each low-level create/delete/replace function, and one
  transition-validator call.
- **Authority policy:** the retained decoder seam is excluded from the temporary
  sidecar-authority inventory only by exact path, approved definition scope, and
  benign symbol. Adversarial fixtures prove that store writes inside either named
  decoder and inside unexpected helpers remain visible. The six frozen authority
  totals remain exactly core authority 115, locked-error handoff 15, lease
  observers 30, heartbeats 167, sidecar correctness 861, and MCP save/recovery
  authority 251. The existing model and sidecar ARCH105–ARCH107 records were
  refreshed for their required decoder symbols; no new architecture allowance was
  introduced.
- **Agents and reviews:** independent model/transition and sidecar workstreams each
  received Sol/xhigh adversarial review and re-review, followed by a separate
  integrated review. Findings covering schema bypass, secret-bearing diagnostic
  values, exception chains, deep JSON recursion, incomplete forbidden-transition
  oracles, direct construction, overbroad authority exclusions, and aliased mutable
  store calls were fixed. All final reviews report no blocking, important, or
  non-blocking finding.
- **Docker validation:** exact images, commands, counts, and results are recorded in
  §11.4. The final baked affected suite passed 373 with three Windows-only skips,
  production lint checked 952 files, Compose `unit` passed, and branch-built
  preflight/core/e2e passed with both strict verdicts zero.
- **Stage result and next:** Stage 2 is complete. Resume with Phase 8 only to
  introduce the authority-free gateway runtime; Phase 7 is not an integration gate,
  so the parent gitlink remains at the Phase 5 integration revision.

#### 2026-08-03 — Phase 6 complete: LeaseClientManager defined normally

- **Phase delivery:** `LeaseClientManager` now owns construction, representation,
  connection state, credential and alias custody, heartbeat compatibility, and
  redaction in one normal class body. The former credential, heartbeat, status,
  binder, and initializer modules are declarative import-only shims. Every old
  defining-module import remains available; the legacy free-function `manager=`
  keyword signatures, binder path and return behavior, initializer behavior, and
  public class construction signature remain frozen without import-time mutation.
- **Explicit compatibility values:** the public `freecad_mcp.lease_manager` facade
  exports immutable `NativeSessionHandle` and `LeaseCompatibilityResult` values.
  The handle contains only one opaque native-session identifier and renders it
  redacted. Compatibility results retain only copied JSON diagnostics, return a
  fresh copy on every access, render no values, accept the frozen public instance
  diagnostics, and reject or fully redact credential, capability, authorization,
  permission, grant, and secret material across nested values, compound names,
  camel/acronym spellings, separators, and encoded textual fragments.
- **Authority and policy:** no legacy authority category grew. The exact frozen
  counts remain core authority 115, locked-error handoff 15, lease observers 30,
  heartbeats 167, sidecar correctness 861, and MCP save/recovery authority 251.
  Heartbeat symbols moved from the retired operation/binding modules into the
  defining manager while the Phase 18 allowance paths changed accordingly. The
  existing facade ARCH106/ARCH107 records grew only for the two required public
  read-only values; no new architecture allowance was introduced.
- **Agents and reviews:** production and contract workstreams received independent
  adversarial review, followed by integrated re-review. Findings covering missing
  public exports, shim side effects, old keyword signatures, the former binder
  import, subclass initializer dispatch, deep immutability, exception/repr leaks,
  and adversarial structured and scalar authority spellings were fixed and
  re-reviewed. The final integrated review reports no blocking, important, or
  non-blocking finding.
- **Docker validation:** exact images, commands, counts, and results are recorded
  in §11.4. The final baked affected suite passed 271, production policy/lint
  checked 951 files, Compose `unit` passed, and the branch-built preflight/core/e2e
  lane passed against the current nested worktree.
- **Stage result and next:** Stage 2 is in progress with Phase 6 complete. Resume
  with Phase 7 only to isolate immutable historic lease decoders; do not begin the
  gateway-runtime stage early.

#### 2026-08-03 — Stage 1 complete: client migrated and XML-RPC retired

- **Phase 5 delivery:** the MCP client, isolated launcher, live-dirty smoke script,
  and lifecycle tests now use JSON-RPC 2.0 end to end. The client validates exact
  protocol negotiation, response IDs, singleton framing headers, bounded bodies,
  and absolute response deadlines. All 75 documented success-shaped failure
  examples become native `JsonRpcRemoteError` instances with structured data;
  unchanged errors retain object identity and peer-echoed session or lease secrets
  are recursively redacted.
- **Surviving listener:** `/jsonrpc` is the only dispatching route. `/` and `/RPC2`
  return the frozen bounded HTTP 410 JSON retirement response without reading or
  dispatching the body. Explicitly incompatible or duplicate protocol headers
  return the frozen HTTP 409 / `-32005` mismatch response before identity capture.
  Duplicate or conflicting framing, non-ASCII-decimal lengths, oversized or short
  bodies, incomplete headers, and slow-drip peers are rejected under one absolute
  header/body deadline. The old `ip_filter` names, including its private parser,
  remain import-compatible.
- **Cancellation and lifecycle:** task teardown sends authenticated
  `invoke_v2_control` as a JSON-RPC notification while the acknowledged public
  cancellation API remains available. Launcher readiness, HMAC proof, identity
  verification, manifest persistence, and deterministic disconnect behavior are
  preserved. No live `ServerProxy(` call remains in production or scripts.
- **Contracts and authority:** the semantic fixture now freezes XML retirement and
  version negotiation while retaining the encoding-independent RPC schema. The
  two client codec vendors are byte-identical at SHA-256
  `a41bd9117c5881e0455115850937e11ec52ba36810ce114e7e4daf93c220530f`.
  The pure HTTP client transport is explicitly excluded from the Phase 18
  save/recovery-authority module census, but its AST symbols remain scanned; the
  frozen authority allowances and heartbeat census are otherwise unchanged.
- **Agents and reviews:** client, listener/retirement, and script/contract
  workstreams received independent adversarial review followed by integrated and
  post-gate re-review. Findings covering duplicate request/response headers,
  Content-Length ambiguity, transfer encodings, slow drip, direct-header secret
  echoes, old private imports, and the authority census were fixed and re-reviewed.
  Every final review reports no blocking, important, or non-blocking finding.
- **Docker validation:** exact images, commands, counts, and results are recorded
  in §11.4. The baked-image contract suite passed 244, production lint checked 949
  files, all four Compose services passed, native App/Gui/Part and the exact GUI
  filter passed, and branch-built preflight/core/e2e passed. An initial App test
  failure was traced to a read-only test working directory; its writable ephemeral
  `/tmp` rerun and the full App suite passed without a source change.
- **Stage result and next:** Stage 1 is complete. The parent gitlink advances at
  this integration gate. Resume with Phase 6 only; do not start Phase 7 early.

#### 2026-08-03 — Phase 4 complete: dual JSON-RPC transport added

- **Phase delivery:** the existing bounded listener now serves legacy XML-RPC at
  `/RPC2` and JSON-RPC 2.0 at `/jsonrpc` on the same host and port. Both encodings
  capture the same MCP identity headers, enter the same registered `FreeCADRPC`
  dispatcher, and share the three general plus two reserved control lanes. Named
  JSON parameters are signature-bound before conversion to the existing positional
  dispatch seam; unknown methods and invalid parameters use the standard JSON-RPC
  errors without bypassing lease enforcement.
- **Framing and bounds:** the byte-identical shared protocol vendors add strict
  UTF-8 JSON framing, request/batch/notification handling, `null` and signed 64-bit
  values, non-finite/lone-surrogate rejection, 4 MiB payload, 1,024-member batch,
  128-level depth, and 100,000-item structural limits. Admission-time socket
  timeouts bound incomplete headers and bodies; declared-length mismatches cannot
  dispatch. Notification-only input produces no JSON body.
- **Structured errors:** explicit legacy `ok: false` and `success: false` results
  become JSON-RPC errors. Exact conflict, stale, cancellation, and lifecycle
  categories use integer application codes while the stable semantic code and
  diagnostic context remain in redacted, independently copied `error.data`.
  Nested authenticated public errors, replay `claimable` extensions, and stale
  state at both supported locations are preserved. Unexpected exceptions remain
  opaque on the wire and in logs.
- **Contracts:** both listeners satisfy the frozen semantic surface. The focused
  suite covers every frozen result example, live same-port XML/JSON dispatch,
  named and positional validation, batches, notifications, malformed/deep/wide
  payloads, saturation, IP filtering, shutdown, short EOF and stalled-header
  clients, signing proof stability, and replay identity across JSON framing. The
  two protocol copies remain byte-identical at SHA-256
  `8dcb7cc450d2fa203bbdf8e3722ec80545097b246975e9d3b060cf04819106ab`.
- **Agents and reviews:** separate listener and structured-error workers were
  independently reviewed, then the integrated listener/protocol seam received a
  final adversarial review. Findings covering nested public errors, redaction and
  copy independence, state-aware classification, recursion bounds, secret-bearing
  logs, partial bodies, incomplete headers, worker
  exhaustion, and weak socket oracles were fixed and re-reviewed. Both final
  reviews reported no blocking, important, or non-blocking finding.
- **Docker validation:** exact images, commands, counts, and results are recorded
  in §11.4. The final focused suite passed 208, architecture policy checked 946
  production files, all touched-file Ruff checks passed, the final Compose unit
  service passed, and the branch-built preflight/core/e2e lane passed against the
  mounted Phase 4 worktree.
- **Next:** create the single Phase 4 commit, then execute Phase 5. Phase 5 must
  move the client end to end, convert every documented failure, negotiate the
  protocol version explicitly, and replace `/RPC2` with a documented deprecation
  response before its integration gate and parent gitlink update.

#### 2026-08-03 — Stage 1 started: JSON-RPC wire migration

- **Authorization and compatibility decision:** the request to execute Stage 1
  resolves the former Phase 4 question conservatively. Treat the existing RPC
  surface as externally consumed: Phase 4 must keep XML-RPC and JSON-RPC working
  against the same dispatcher, and Phase 5 must replace the XML-RPC listener with
  an explicit documented deprecation response rather than silently removing it.
- **Execution base:** Stage 1 starts from parent
  `eb531e5320d29f7df548a9a3997e9dd66bb5f70c` and nested MCP
  `caff97a1aa1b0862e0e51c4f58ad7223eb163070`. The Phase 1 frozen semantic,
  authority, locator, and registry inputs remain unchanged.
- **In-flight Phase 4 ownership:** the integrator owns the byte-identical shared
  JSON-RPC codec and central dual-listener wiring. Separate workers own the
  listener and structured-error seams; each receives an independent adversarial
  review, followed by an integrated Phase 4 review.
- **Current evidence:** the shared codec's focused Docker suite passes 17/17 and
  its touched-file Ruff gate passes. This is interim evidence only; Phase 4 remains
  in progress until both listener paths, semantic contracts, reviews, the complete
  Docker gate, and the collaboration cross-track lane pass.
- **Resume:** finish Phase 4, replace this entry with the complete delivery and
  record exact evidence in §11.4, create the single required Phase 4 commit, then
  continue automatically through Phase 5 and its integration gate.

#### 2026-08-03 — Phase 3 complete: shared protocol extracted

- **Phase delivery:** both process layouts now contain a 26-file
  `_shared/protocol/` package. The add-on and client copies are byte-identical,
  use canonical UTC normalization, and own the manifest, proof, handshake,
  credential, replay, session, validation, redaction, and public-error types.
  Existing `lease_protocol*` and `rpc_auth*` paths remain declarative import-only
  compatibility shims; their public names and behavior are unchanged.
- **Internal migration:** production consumers under both package roots import the
  canonical protocol leaves. The add-on copy remains standard-library-only and no
  FreeCAD, Qt, document-authority, lifecycle, dirty-state, sidecar-correctness, or
  recovery-policy dependency was introduced. Standalone scripts outside the two
  production package roots remain public-facade consumers.
- **Frozen contracts:** byte equality is asserted without counting the vendored
  copy twice. The semantic RPC fixture and all old import paths remain valid. The
  Phase 1 authority census remains exactly `core_authority=115`, `heartbeats=167`,
  `lease_observers=30`, `locked_error_handoff_rotation=15`,
  `mcp_save_recovery_authority=251`, and `sidecar_correctness=861`; the locator
  census remains 514 nodes, 504 references, and 432 runtime calls, with 37 dynamic
  lookups and 22 local-import locators.
- **Policy hardening:** structurally paired import-fallback shims are recognized
  without admitting same-arm effects, and the `constants.py` exception now accepts
  only cohesive locally assigned immutable public constants. Import façades,
  runtime-produced values, and mutable values fail focused negative fixtures. The
  allowance ledger contains 1,054 exact findings: ARCH101 87, ARCH103 573,
  ARCH104 301, ARCH105 19, ARCH106 31, and ARCH107 43. The one Phase 3-adjusted
  ARCH107 record retains the legacy 28-symbol constants compatibility façade and
  requires Phase 23 to remove the structural allowance without removing the shim.
- **Agents and reviews:** separate shared-protocol/client and add-on/shim
  workstreams were independently reviewed, followed by adversarial integrated
  review. Findings around import-fallback effects, false-positive cohesive
  constants, standalone public-facade consumers, UTC normalization, compatibility
  shims, and allowance wording were fixed. The final integrated review reported no
  blocking, important, or non-blocking finding.
- **Docker validation:** exact images, commands, counts, and results are recorded in
  §11.4. Production architecture policy and Ruff passed for 942 files; the focused
  policy suite passed 91 and the integrated focused suite passed 191. All four final
  Compose services and the complete branch-built native/cross-track integration
  lane passed.
- **Next/blocker:** Stage 0 is complete. Before Phase 4, confirm whether anything
  outside this repository calls the current RPC surface (including user macros,
  other add-ons, and scripts against the port); that answer determines the public
  compatibility obligation for the dual-listener migration.

#### 2026-08-03 — Phase 2 complete: boundary policy replaces size rules

- **Phase delivery:** `ci/lint_python.py` no longer contains ARCH001/ARCH002,
  line-count, or class-count enforcement. ARCH101–ARCH107 now enforce capability
  ownership, add-on layer direction, application runtime locator removal, internal
  leaf imports, declarative shim purity, a 16-symbol explicit public-surface budget,
  and the mixed-responsibility/giant-façade backstop. Ruff `C901` remains the
  function-complexity rule.
- **Structural behavior:** relative and aliased imports are resolved before ownership
  and layer checks; runtime plus transport/dispatch are explicit multi-capability
  composition seams; capability subjects remain isolated. Locator aliases are
  rejected while the frozen Phase 1 inventory remains exact. Explicit but
  unauditable `__all__` fails closed, import-only and hybrid façades count their
  public bindings, and import-plus-`__all__` shims are recognized without relying on
  prose markers.
- **Allowances:** `ci/architecture_policy_allowances.json` contains 1,052 exact
  code/path/line/column/fingerprint records with reasons and removal phases:
  ARCH101 87, ARCH103 573, ARCH104 301, ARCH105 20, ARCH106 27, and ARCH107 44.
  There are no ARCH102 allowances and no glob or module-wide waiver. Stale, moved,
  changed, and newly introduced occurrences fail independently.
- **Focused contract:** 85 synthetic cases cover cohesive multi-class values,
  exact 16/17 public surfaces, dynamic and augmented `__all__`, mutable and
  alternate-worded shims, function/import/hybrid façades, exact capability
  taxonomy, relative layer imports, barrel resolution, aliased locators, composition
  roots, mixed definitions inside a declared capability, class-method façades,
  `TYPE_CHECKING` else effects and qualified guards, nested/destructive `__all__`
  mutation, public/private class methods, assignment-bound exports, builtin and
  assignment-aliased runtime locators, anchored add-on layers/composition seams, both
  add-on package spellings, package-`__init__` and child-package barrel imports, and a
  non-discoverable source specimen that Ruff alone rejects with exactly one C901
  diagnostic and no other code. Module-executed conditional, loop-destructured,
  tuple, named-expression, and destructive bindings are covered; ordinary dependency
  names and generic builtin imports remain valid, while add-on dispatch rejects the
  authoritative stdlib/internal-only boundary. Comprehension-local bindings remain
  scoped; structurally paired fallbacks preserve the frozen census without hiding an
  unrelated, same-arm, or nested-scope locator; definition/import bindings of
  `__all__` fail closed. Static and dynamic imports share the same layer-direction
  checks, direct and aliased dynamic FreeCAD/Qt imports fail at the gateway, both
  package spellings remain valid internal targets, and aliased `TYPE_CHECKING`
  guards remain declarative.
- **Agents and reviews:** independent boundary and shape fixture workstreams were
  followed by adversarial Sol/xhigh reviews. Findings around relative imports,
  locator aliases, taxonomy, composition roots, shim detection, public-surface
  fail-open behavior, façade binding counts, Ruff ownership, and oracle strength
  were fixed; both workstream re-reviews reported no remaining finding. Integrated
  reviews then found adversarial gaps around declared-package and assignment-bound
  mixing, class visibility, `TYPE_CHECKING` forms, destructive `__all__`, equivalent
  locators, barrel variants, path-insensitive layer/composition detection, fallback
  branch structure, dynamic layer imports, and policy-function complexity. All
  reported gaps were fixed; the final integrated re-review reported no blocking,
  important, or non-blocking finding.
- **Runtime/contracts:** no add-on or client production runtime file changed; public
  imports, RPC behavior, registry order, and the Phase 1 collaboration/authority
  inventories remain unchanged.
- **Docker validation:** exact results and image identity are recorded in §11.4.
  Both production lint modes checked 888 Python files and passed; the focused policy
  suite passed 85; the complete Compose unit service passed.
- **Next:** execute Phase 3 only. Phase 2 is not an integration gate, so the parent
  gitlink remains at the Phase 1 integration revision.

#### 2026-08-03 — Phase 1 complete: native collaboration baseline frozen

- **Phase delivery:** `test(mcp): freeze the native collaboration baseline` records
  parent base `863535a2d4b6c33b5bfce8171762320060a34afb`, nested MCP base
  `5357d0c16a64b4981a5f508bc83dd07ddf4f1ca6`, and native prerequisite
  commits `8593f781ac`, `2e4336f39a`, `69b12a53d6`, `60ff7d9b22`,
  `02476edba1`, and `300bbbcf5a` for native Phases 1–6.
- **Frozen inventories:** the committed planned-pre-cutover manifest records all six
  temporary authority classes with exact occurrence paths and Phase 18 negative end
  states. It freezes 514 `_rpc_mod` AST locator nodes (10 definitions plus 504
  syntactic references, including 432 runtime calls), 37 equivalent dynamic module
  lookups, 22 local-import locators, seven retained compatibility surfaces, and 22
  public lease RPC adapters. Exact occurrence records, rather than globs, are the
  allowance boundary.
- **Frozen public contracts:** the semantic RPC fixture now describes all 84 public
  methods as transport-neutral parameter, result, and normalized-error schemas with
  examples. The production XML-RPC dispatcher matches the listener specimens and
  round-trips every semantic outcome. The registry fixture freezes 170 tools in
  effective insertion order and 47 registration modules.
- **Native boundary:** the branch lane proves all recorded App document/module
  methods and the exact embedded-GUI-Python test
  `CollaborationDomainIntegrationTest.pythonPersonalContextStorageApiIsCallable`.
  The Compose image remains adapter-only because its conda FreeCAD has no branch
  collaboration bindings; every later collaboration-touching phase therefore also
  runs the branch-built lane.
- **Implementation impact:** tests, helpers, fixtures, and this plan changed; no
  production runtime file changed. The only Phase 1 re-scope is the Phase 12 native
  compatibility-mutation binding recorded in the next entry; the phase list is now
  fixed under §5.5.
- **Agents and reviews:** independent native-baseline and MCP-census workstreams were
  followed by adversarial native, census, and integrated Sol/xhigh reviews. Important
  findings around semantic result specimens, indirect authority paths, ACL false
  positives, compatibility inversion, and GUI Python execution evidence were fixed
  and re-reviewed. The final integrated review reported no blocking or important
  finding.
- **Docker validation:** images and exact results are recorded in §11.4. Architecture
  lint checked 888 production Python files; full Ruff passed. All four Compose
  services, native App/Gui/Part suites, the exact GUI binding test, preflight, and
  branch-built MCP core/e2e jobs passed.
- **Next:** execute Phase 2 only; do not broaden any temporary authority allowance.

#### 2026-08-03 — Phase 1 verified and re-scoped the Phase 12 native binding seam

- **Verified fact:** native Phase 6 contains
  `DocumentCollaborationService::commitCompatibilityMutation` and the corresponding
  GUI compatibility executor, but neither is available to Python. Without a binding,
  MCP compatibility mutations could not enter the native commit barrier before the
  Phase 18 authority removal.
- **Authorized Phase 1 rescope (§5.5):** Phase 12 is now one logical cross-repository
  delivery. Its parent object adds the minimal synchronous UnknownModel-only
  `DocumentPy` binding and focused native tests; its nested object routes MCP callers
  and removes the affected locators. The parent commit is canonical and advances the
  nested gitlink.
- **Boundary constraints:** the binding accepts no caller stable identity, owner,
  token, generation, confirmation boolean, TLS/capability grant, or revision-neutral
  serialization callback. It enters through the GUI dispatcher, manages the GIL
  during owner-thread dispatch, propagates Python exceptions into native rollback,
  and returns the native structured result.
- **Reason this does not transfer authority:** FreeCAD still assigns identity,
  performs lifecycle/reentrancy checks, owns rollback and publication, and decides
  the outcome. Python supplies only the compatibility callback body.
- **Phase status:** Phase 1 remains in progress until its reviews and complete Docker
  integration gate pass; this entry records the only phase-list rescope permitted by
  §5.5 and does not mark the phase complete.

#### 2026-08-03 — Collaboration cutover absorbed; plan expanded to 23 phases

- **Decision:** start this plan after native collaboration Phases 1–6. The former
  standalone collaboration Phase 7 is not a prerequisite or a separate delivery;
  its adapter and cutover obligations are now owned here.
- **Reason:** the prior plans formed a cycle: collaboration Phase 7 expected a
  stabilized MCP, while this plan required collaboration Phase 7 to have removed the
  lease authority before MCP work began.
- **Baseline change:** phase 1 records the native Phase 6 parent plus the live
  pre-cutover MCP tree, commits a planned compatibility manifest and complete removal
  inventory, and freezes every temporary authority path as a named allowance.
- **Ordering change:** phases 6–17 prepare compatibility surfaces, native routing,
  and deterministic bootstrap without expanding legacy authority. New Phase 18 then
  removes the live MCP lease/sidecar/heartbeat/save-recovery authority and the parent
  `McpOwned`/TLS/takeover surface in one cross-repository integration delivery.
- **Renumbering:** typed registration is phase 19, manifests/generation are phases
  20–22, and final enforcement is phase 23.
- **Live state checked:** the parent records MCP gitlink
  `fa98ad32a4dd80076200e1850a3169a67132566a`; the selected nested base is
  `49b2dfda63caa9915e15949889d8612c7816fbc2`, whose committed content tree matches
  the gitlink. This plan file is the only nested worktree change. Native
  authority files and legacy MCP authority paths remain present, while the planned
  collaboration client/bridge and final compatibility manifest are absent, matching
  the new pre-cutover baseline.
- **Next:** execute phase 1 only.

#### 2026-08-02 — Architecture redesigned; 70 phases reduced to 22 (superseded by 2026-08-03 ordering)

- **Base revisions:** authoring-time only; execution revisions intentionally TBD.
- **Superseded:** the previous 70-phase plan and its 2026-08-02 "Chaptered plan ready"
  entry. That plan was authored against the pre-cutover tree and sized its Stage 2
  (17 phases of ports and nine use-case handlers) and Stage 5 (25 phases of file
  relocation) against code the prerequisite either deletes or leaves as deprecation
  stubs. Its Composer/Cursor worker policy also contradicted the prerequisite's Codex
  policy.
- **Architecture decisions:**
  - Keep two processes. Crash isolation, the headless-worker isolation model, and a
    stdlib-only add-on outweigh the duplication the split costs.
  - The add-on becomes three layers plus one composition root. No ports-and-adapters
    layer beyond `transport` and `dispatch`, because post-cutover there is no policy
    left in Python to protect.
  - Move the wire to JSON-RPC 2.0. MCP is already JSON-RPC 2.0, so this removes a
    re-encode at the midpoint and lets failures travel as errors instead of inside
    success-shaped envelopes. Encoding and channel are decoupled; the permissioned-socket
    change is deferred to its own spike because `AF_UNIX` on Windows needs proving.
  - One vendored protocol module with a byte-equality gate replaces the two
    implementations and the permanent conformance-vector apparatus.
  - Declare each capability once in a per-subject manifest; generate registration,
    client stubs, and gateway dispatch; assert byte-equality against the frozen
    registry snapshot.
  - Retire ARCH001/ARCH002 in Stage 0 rather than at the end, since they are what
    produced the 31 line-count splits and would distort every intermediate state.
- **Review findings incorporated:** phase 1 may re-scope the phase list (§5.5) rather
  than only stopping; phase 1 derives the compatibility manifest if the prerequisite
  does not publish one (§4.1); the compose-lane limitation is a recorded phase-1
  decision (§4.1 item 5); the worker policy now matches the prerequisite's (§5.1); the
  parent gitlink is bumped at integration gates so the cross-track lane does not test
  the pre-refactor add-on (§5.4); the locator census is recorded per module (§4.1 item 4).
- **Open question blocking phase 4:** whether anything outside this repository calls the
  RPC surface — user macros, other add-ons, scripts against the port. If nothing does,
  the frozen XML-RPC surface is a refactor safety net rather than a public contract.
- **Contracts/shims:** no implementation or public surface changed; document only.
- **Next:** wait for the collaboration prerequisite through its phase 7, then execute
  phase 1 only.

#### 2026-08-02 — Chaptered plan ready (superseded)

- Retained for history. Its 70-phase list, Stage 0–7 structure, Composer/Cursor worker
  policy, and per-phase four-service Docker gate are replaced by the entry above.

### 11.4 Phase evidence

Append evidence newest-first. Image IDs are used when the local image has no
repository digest; host-side build or test output is never evidence.

#### Phase 7 — `refactor(mcp): isolate legacy lease decoders`

- **Images:** final Compose `freecad-mcp-tests:latest` at
  `sha256:5815335147e3f95d16634ee0e7d64bb171a8bcb4e647dcacfcc1ae5cc7be2198`;
  preserved native `freecad-collaboration-ci:ubuntu24.04-20260801` at
  `sha256:b34e0e1ecabafa22c760850548b7e8239c4a3428c7d4084927ed5d1109f5142f`;
  cross-track `freecad-ci-mcp:24.04-phase1` at
  `sha256:4ea79d64874ce74eddd8689bbcb8560cc7215a8603d28e6a0b45da8f64defcc3`.
  The local daemon reports no repository digest for these images.
- **Baked-image contracts and lint:** `ci/lint_python.py addon/FreeCADMCP
  src/freecad_mcp` checked 952 production files and passed architecture policy and
  Ruff. The final historic decoder, live model/sidecar/service, public and legacy
  import, observer, Git-sidecar, baseline, and architecture-policy selection passed
  373 with the three Windows-DACL cases skipped. The dedicated historic model and
  sidecar modules contribute 14 and eight passing contracts respectively.
- **Compose phase gate:** after `docker compose build`, `docker compose run --rm
  unit` selected 2,045: 2,041 passed, the three Windows-DACL tests skipped, and the
  existing screenshot test xfailed; 129 non-unit tests were deselected. Phase 7 is
  not an integration gate, so §5.7 requires this unit service rather than all four
  Compose services.
- **Branch-built cross-track:** the preserved `freecad-phase3-debug` volume and
  branch hash `7a47b18044b82bb2eb1c17047150d72eadde6c26` were reused because no native
  source changed. The unmodified preflight wrapper emitted `PREFLIGHT_OK`. With
  `FREECAD_MCP_REQUIRE_NATIVE_COLLABORATION=1`, the unmodified core wrapper
  collected 12: seven passed and five expected xfailed; the unmodified e2e wrapper
  passed 117/117. Both strict verdict files contained zero and were removed with
  their generated XML reports after recording.
- **Review and authority result:** both workstream re-reviews and the final
  integrated review are clear with no blocking, important, or non-blocking finding.
  The immutable-decoder exemption's adversarial write probes pass, aliased
  create/delete/replace calls remain visible, the 72-call Phase 18 census is exact,
  and all six frozen authority-category counts remain unchanged.

#### Phase 6 — `refactor(mcp): define LeaseClientManager normally`

- **Images:** final Compose `freecad-mcp-tests:latest` at
  `sha256:287abb5527584644427dcc79a59a666d285bd6050d6975724c7ccb5e521709d8`;
  preserved native `freecad-collaboration-ci:ubuntu24.04-20260801` at
  `sha256:b34e0e1ecabafa22c760850548b7e8239c4a3428c7d4084927ed5d1109f5142f`;
  cross-track `freecad-ci-mcp:24.04-phase1` at
  `sha256:4ea79d64874ce74eddd8689bbcb8560cc7215a8603d28e6a0b45da8f64defcc3`.
- **Baked-image contracts and lint:** `ci/lint_python.py addon/FreeCADMCP
  src/freecad_mcp` checked 951 production files and passed. Ruff passed for the
  Phase 6 test module. The final manager, compatibility, recovery, lifespan,
  baseline, and architecture-policy selection passed 271/271; the focused Phase 6
  contract module passed 50/50 after the final adversarial redaction fixes.
- **Compose phase gate:** after `docker compose build`, `docker compose run --rm
  unit` selected 2,020: 2,016 passed, the three Windows-DACL tests skipped, and the
  existing screenshot test xfailed; 129 non-unit tests were deselected. Phase 6 is
  not an integration gate, so §5.7 requires this unit service rather than all four
  Compose services.
- **Branch-built cross-track:** the preserved `freecad-phase3-debug` volume and
  branch hash `7a47b18044b82bb2eb1c17047150d72eadde6c26` were reused because no native
  source changed. The unmodified preflight wrapper emitted `PREFLIGHT_OK`. With
  `FREECAD_MCP_REQUIRE_NATIVE_COLLABORATION=1`, the unmodified core wrapper
  collected 12: seven passed and five expected xfailed; the unmodified e2e wrapper
  passed 117/117. Both strict verdict files contained zero and were removed with
  their generated XML reports after recording.
- **Review result:** production, contract, and final integrated adversarial reviews
  are clear. Every blocking or important finding was fixed and re-reviewed; no
  final non-blocking finding remains. The exact authority-census equality contract
  passes with unchanged category counts.

#### Phase 5 — `refactor(mcp): migrate to JSON-RPC and retire XML-RPC`

- **Images:** final Compose `freecad-mcp-tests:latest` at
  `sha256:7c9ded3f5b5328dafabad4a00d889a4819f4e13b29485398f063eff8056db961`;
  preserved native `freecad-collaboration-ci:ubuntu24.04-20260801` at
  `sha256:b34e0e1ecabafa22c760850548b7e8239c4a3428c7d4084927ed5d1109f5142f`;
  cross-track `freecad-ci-mcp:24.04-phase1` at
  `sha256:4ea79d64874ce74eddd8689bbcb8560cc7215a8603d28e6a0b45da8f64defcc3`.
  The local daemon reports no repository digest for these images.
- **Baked-image contracts and lint:** `ci/lint_python.py addon/FreeCADMCP
  src/freecad_mcp` checked 949 production files and passed. Ruff passed for every
  touched script and test. The final protocol, native-error, client transport,
  listener retirement, semantic RPC, isolated-script, cancellation, authority
  baseline, registry, and shared-protocol selection passed 244/244. The larger
  integrated selection passed 230/230 before the baseline additions; independent
  final review reproduced 149 focused tests and one real-FreeCAD lifecycle test.
- **Compose integration gate:** after the final `docker compose build`, `unit`
  selected 1,970: 1,966 passed, three Windows-DACL tests skipped, and the existing
  screenshot test xfailed; 129 were deselected. `e2e` selected 117: 115 passed and
  two adapter-only native tests skipped. `core` selected 12: four passed, one
  adapter-only native test skipped, and seven expected xfailed. `benchmark` passed
  1/1. The commands were the four unmodified §10 Compose services.
- **Native branch gate:** the preserved `freecad-phase3-debug` Docker volume was
  exercised with branch hash `7a47b18044b82bb2eb1c17047150d72eadde6c26`.
  From writable ephemeral `/tmp`, `App_tests_run` ran 747: 745 passed and the two
  known BackupPolicy tests skipped. `Part_tests_run` passed 342/342. Under Xvfb,
  llvmpipe, and `QT_QPA_PLATFORM=xcb`, `Gui_tests_run` passed 240/240 and exact
  `CollaborationDomainIntegrationTest.pythonPersonalContextStorageApiIsCallable`
  passed 1/1. The App test's diagnostic writable-directory filter also passed 1/1.
- **Cross-track jobs:** the unmodified preflight wrapper emitted `PREFLIGHT_OK`.
  With `FREECAD_MCP_REQUIRE_NATIVE_COLLABORATION=1`, the unmodified core wrapper
  collected 12: seven passed and five expected xfailed; the e2e wrapper passed
  117/117. Both strict verdict files were zero and were removed after recording.
- **Review result:** all workstream reviews, the integrated adversarial review, and
  the post-unit authority-census re-review are clear. Every blocking or important
  finding was fixed and re-reviewed; no final non-blocking finding remains.

#### Phase 4 — `feat(mcp): add the JSON-RPC 2.0 transport`

- **Images:** final Compose `freecad-mcp-tests:latest` at
  `sha256:b85cbbe5bfc7c83846ff01023c28f82770886cc3a6faae9de405a7f81aeb1f64`;
  preserved native `freecad-collaboration-ci:ubuntu24.04-20260801` at
  `sha256:b34e0e1ecabafa22c760850548b7e8239c4a3428c7d4084927ed5d1109f5142f`;
  cross-track `freecad-ci-mcp:24.04-phase1` at
  `sha256:4ea79d64874ce74eddd8689bbcb8560cc7215a8603d28e6a0b45da8f64defcc3`.
  The local daemon reports no repository digest for these images.
- **Focused contracts and lint:** a final bind-mounted Docker run passed 208/208
  JSON framing, structured-error, dual-listener, frozen semantic, concurrency,
  shared-protocol, authentication, replay, lifecycle, idempotency, and cancellation
  tests. The exact production architecture command checked 946 Python files and
  passed. Production touched-file lint passed for nine files; Ruff passed for the
  five touched test modules. Independent review verified byte equality at the
  SHA-256 recorded in §11.3 and reproduced the slow/partial-client boundaries
  after their fixes.
- **Compose phase gate:** after rebuilding the final image, `docker compose run
  --rm unit` selected 1,909: 1,905 passed, three Windows-DACL tests skipped, and
  the existing screenshot test xfailed; 129 non-unit tests were deselected.
- **Branch-built cross-track:** no native source changed, so the final Phase 3
  `freecad-phase3-debug` build volume was reused and the current nested worktree
  was mounted over the parent checkout. The unmodified preflight wrapper emitted
  `PREFLIGHT_OK` with pytest 9.1.1 and FreeCAD 26.3.0 revision 48071, branch
  `feature/assembly-interference-detection`, hash
  `7a47b18044b82bb2eb1c17047150d72eadde6c26`. With
  `FREECAD_MCP_REQUIRE_NATIVE_COLLABORATION=1`, the unmodified core wrapper
  collected 12: seven passed and five expected xfails with no real skip; the
  unmodified e2e wrapper passed 117/117. Both strict verdict files were zero and
  were removed after the run.
- **Review result:** structured-error and listener/protocol reviews are clear.
  Every reported blocking or important finding was fixed and re-reviewed; the
  final reviews found no remaining finding.

#### Phase 3 — `refactor(mcp): extract the shared protocol module`

- **Images:** final Compose `freecad-mcp-tests:latest` at
  `sha256:0ae761f034b66310a647fdd206961ea71889424e7bdca91de84408e4d7b80327`;
  native `freecad-collaboration-ci:ubuntu24.04-20260801` at
  `sha256:b34e0e1ecabafa22c760850548b7e8239c4a3428c7d4084927ed5d1109f5142f`;
  cross-track `freecad-ci-mcp:24.04-phase1` at
  `sha256:4ea79d64874ce74eddd8689bbcb8560cc7215a8603d28e6a0b45da8f64defcc3`.
  The local daemon reports no repository digest for these images.
- **MCP lint and focused contracts:** final-image architecture policy and full Ruff
  each checked 942 production files and passed with Ruff 0.16.1. The focused
  architecture-policy suite passed 91/91; integrated protocol/shim/auth/lifespan
  review tests passed 191/191. Independent verification found 26 Python files in
  each protocol layout with zero byte mismatch, no census expansion, and the 1,054
  exact allowed legacy findings broken down in §11.3.
- **Compose integration gate:** `docker compose run --rm unit` selected 1,823:
  1,819 passed, three Windows-DACL tests skipped, and one existing screenshot test
  xfailed. `e2e` passed 115 with two adapter-only native skips; `core` passed four
  with one adapter-only native skip and seven expected xfails; `benchmark` passed
  one. All four commands used the final image above.
- **Native build:** an isolated Docker build volume preserved the host build tree.
  The branch configured and built `FreeCADCmd`, `FreeCAD`, `App_tests_run`,
  `Gui_tests_run`, `Part_tests_run`, `PartTestData`, `PartScripts`, `Materials`,
  `PartDesign`, `Sketcher`, `Assembly`, `PartDesignScripts`, `AssemblyTests`, and
  `pivy`. LF-normalized Pivy/Coin source overlays were used only inside Docker to
  avoid the Windows bind mount's generated-header truncation issue; host source was
  unchanged. The result identifies as FreeCAD 26.3.0, revision `48071 (Git)`, hash
  `7a47b18044b82bb2eb1c17047150d72eadde6c26`.
- **Native suites:** `App_tests_run` ran 747: 745 passed, the two known BackupPolicy
  tests skipped, and seven tests remained disabled. `Part_tests_run` passed 342/342.
  With Xvfb, llvmpipe, and the fixture-required `QT_QPA_PLATFORM=xcb`,
  `Gui_tests_run` passed 240/240; the exact
  `CollaborationDomainIntegrationTest.pythonPersonalContextStorageApiIsCallable`
  filter passed 1/1.
- **Cross-track jobs:** the unmodified Woodpecker preflight emitted `PREFLIGHT_OK`
  with pytest 9.1.1 and the branch identity above. With the frozen native-API
  requirement enabled, the unmodified core wrapper collected 12: seven passed and
  five expected xfails, with no real skip. The unmodified e2e wrapper passed
  117/117. Both strict JUnit verdict files were zero.
- **Review result:** workstream reviews and the final integrated adversarial review
  are green with no blocking, important, or non-blocking finding. Public RPC and
  old-path import behavior are unchanged.

#### Phase 2 — `build(mcp): replace module size rules with boundary policy`

- **Image:** final Compose `freecad-mcp-tests:latest` at
  `sha256:91767d159ad0b0427f1d2a908449c785c961f62e467c3fd1cddbe9d1b439dd2d`;
  the local daemon reports no repository digest.
- **Architecture policy:** Docker `uv run ci/lint_python.py --architecture-only
  addon/FreeCADMCP src/freecad_mcp` checked 888 production files and passed. Its raw
  policy inventory is 1,052 exact allowed legacy findings with the ARCH101/103–107
  breakdown in §11.3; the ARCH103 component is exactly the Phase 1 census of 514
  `_rpc_mod` nodes, 37 dynamic lookups, and 22 local-import locators.
- **Ruff and focused contracts:** the corresponding full production lint/Ruff
  command passed with final-image Ruff 0.16.1. A separate Docker compatibility run
  pinned Ruff 0.12.12 and passed all touched Python paths. The focused
  `tests/test_architecture_policy.py` suite passed 85/85, including an isolated source
  assertion for exactly one C901 diagnostic; architecture policy did not duplicate it.
- **Compose phase gate:** after `docker compose build`, `docker compose run --rm
  unit` selected 1,810 tests: 1,806 passed, three Windows-DACL tests skipped, and one
  existing screenshot behavior test xfailed; 129 non-unit tests were deselected.
- **Review result:** boundary and shape Sol/xhigh workstream reviews and re-reviews
  are green. The final integrated Sol/xhigh re-review is clear with no blocking,
  important, or non-blocking finding. Production runtime behavior is unchanged.

#### Phase 1 — `test(mcp): freeze the native collaboration baseline`

- **Images:** `freecad-collaboration-ci:ubuntu24.04-20260801` at
  `sha256:b34e0e1ecabafa22c760850548b7e8239c4a3428c7d4084927ed5d1109f5142f`;
  `freecad-ci-mcp:24.04-phase1` at
  `sha256:4ea79d64874ce74eddd8689bbcb8560cc7215a8603d28e6a0b45da8f64defcc3`;
  final Compose `freecad-mcp-tests:latest` at
  `sha256:0bebb40f1d9db2c235d07f1159199894d457636af9430bbd6f5988bcbf56fab6`.
  None has a repository digest in the local daemon.
- **MCP lint/contracts:** Docker `uv run ci/lint_python.py --architecture-only
  addon/FreeCADMCP src/freecad_mcp` checked 888 files and passed; the corresponding
  full lint/Ruff command passed. Focused baseline, semantic RPC/listener, registry,
  and native-API contracts passed 15 tests with the one expected adapter-only native
  skip; the final Compose unit gate subsumed the complete fixture set.
- **Compose integration gate:** after `docker compose build`, `unit` passed 1,721
  with three platform skips and one expected xfail; `e2e` passed 115 with two
  adapter-only native skips; `core` passed four with one adapter-only native skip and
  seven expected xfails; `benchmark` passed one. Commands were the four §10
  `docker compose run --rm` services with their declared markers.
- **Native configure/build:** Docker ran
  `ci/woodpecker/freecad-configure-debug.sh`, then built the gate artifacts and
  required runtime resources with CMake targets `FreeCADCmd`, `FreeCAD`,
  `App_tests_run`, `Gui_tests_run`, `Part_tests_run`, `PartDesign`, `Sketcher`,
  `Assembly`, `PartDesignScripts`, `AssemblyTests`, and `pivy`. The Windows worktree's
  generated Pivy headers were excluded/regenerated with LF endings inside the Docker
  volume before the Pivy target; no host source was changed. The resulting branch
  identity was `26.3.0`, revision `48070 (Git)`, hash
  `863535a2d4b6c33b5bfce8171762320060a34afb`.
- **Native suites:** `App_tests_run` ran 747: 745 passed and two known BackupPolicy
  tests skipped (seven disabled); `Part_tests_run` passed 342/342; Xvfb-backed
  `Gui_tests_run` passed 240/240. The exact personal-context Python binding filter
  passed 1/1.
- **Cross-track jobs:** the unmodified Woodpecker preflight emitted `PREFLIGHT_OK`
  with pytest 9.1.1 and the recorded branch identity. The unmodified core job
  collected 12: seven passed and five expected xfails, with no real skip. The
  unmodified e2e job passed 117/117. Both strict JUnit verdict files were zero.
- **Review result:** native, census, and integrated reviews are green; no blocking or
  important finding remains. Runtime behavior is unchanged.

---

## 12. Integrator cheat-sheet

1. Read §11.1 and the newest §11.3 entry first.
2. Verify native collaboration Phases 1–6 and record the parent and MCP base revisions.
3. Select exactly the next numbered phase from §6; do not skip ahead.
4. Freeze integrator-only shared paths from §5.3.
5. Give each worker exact exclusive source, target, and test paths plus forbidden paths.
6. State the native-authority rule and the public contracts the phase must preserve.
7. Require the §5.6 worker report and an adversarial Sol/xhigh review.
8. Clear blocking and important findings before integration.
9. Apply shared façade, barrel, registry, fixture, generator, and composition changes yourself.
10. Run the §5.7 gate for the phase; run the integration gate where §6 marks it.
11. Verify old-path shims, registry order, semantic RPC contract, and layer direction.
12. Update §11 inside the substantive phase commit.
13. Create the exact phase commit subject from §6.
14. Bump the parent gitlink at integration gates per §5.4.
15. Never add a phase squash, merge, shim-removal, or validation-only commit.
