# Typed RPC operations audit — `feature/typed-rpc`

**Snapshot as of roundup: 2026-09-13** (Europe/Amsterdam). Campaign paused for handover; no further op migrations in this session.

**typed-rpc-platform LANDED** (Composer 2.5). Grok PASS (req 1–8). MCP `374a59b` + parent `07d75f0497` pushed; PRs open. Tip and parallel op forks **NOT PASS** — interrupted for roundup.

> **Canonical location:** moved from gitignored `.idea/feature_typed-rpc_progress.md` to `tools/mcp/freecad-mcp/doc/feature_typed-rpc_progress.md` (this file). The `.idea/` copy may still exist locally but is not the source of truth.

## Orchestration

- Parent checkout: `D:/code/FreeCAD`
- Progress tracker: `tools/mcp/freecad-mcp/doc/feature_typed-rpc_progress.md` (formerly `.idea/feature_typed-rpc_progress.md`)
- Reference: `ci/qualify_body_create.py` + `ci/check_body_create_contract.py` (Body reference implementation)
- Models (local only): orchestrator/reviewer `cursor-grok-4.6-xhigh`; implementer `composer-2.5`; forbidden Fast/Cloud/Auto/substitutes
- Merge: leave final merge to Rchiemstra
- Git: commit/push MCP submodule first, then parent submodule pointer; open PRs and wait for required CI

## Policy

- Independent operations get separate Git worktrees/branches and isolated MCP submodule checkouts.
- Overlapping files are sequential.
- Mutations: native capability required, one admitted document, native transaction, recompute before inspection, no postcondition writes, verify rollback.
- Typed boundaries: no explicit or imported `Any`; strict versioned responses; preserve uncertainty; no cached success after native rejection.
- Tests must cover real MCP schema dispatch, authenticated JSON-RPC, native failures, and deliberately broken variants including the actual CI failure path.
- Do not claim PASS if review or evidence is incomplete.
- Do not hand-edit `src/freecad_mcp/generated/**`. Regenerate with `python scripts/generate_capability_shadow.py` (calls `write_production_outputs` + shadow). Manifest bootstrap: `python scripts/bootstrap_capability_manifests.py`.

## Git identity (roundup 2026-09-13)

| Repo | Branch | HEAD | Dirty | Worktrees |
| --- | --- | --- | --- | --- |
| Parent `D:/code/FreeCAD` | `feature/typed-rpc` (tracks `origin/feature/typed-rpc`) | `07d75f049719b48d72590d07452be6f67732bd4d` | clean (pre-doc commit) | main + 4 op worktrees |
| MCP submodule `tools/mcp/freecad-mcp` | `feature/typed-rpc` (tracks `origin/feature/typed-rpc`) | `374a59b7f8e74e6f15c6326db00abdd5fb0f3f38` | doc files pending commit | submodule gitdir + isolated MCP worktrees |
| Tip worktree `D:/code/FreeCAD-wt-body-set-tip` | `feature/typed-rpc-body-set-tip` | `07d75f049719b48d72590d07452be6f67732bd4d` | **Tip-only files unstaged** | **NOT PASS** — unpark incomplete |

Parent HEAD message: `Point MCP at typed RPC discovery and run discoverable contract gates in Woodpecker.`
MCP HEAD message: `Add typed RPC discovery so new CAD ops register without serializing pyproject or Woodpecker.`

Reference qualification used older bases (do not confuse with current HEAD):

| Baseline | SHA |
| --- | --- |
| Parent at body_create qualify | `b253505340ce45d0d6720bc9894f0e063e6196e5` |
| MCP at body_create qualify | `c4fa4f5562e2319606945efc7c1aa0767ad5f9d9` |

Current HEADs are **descendants** of those baselines (body_create harden + parent lint pin). This inventory did **not** re-run `ci/qualify_body_create.py`. `body_create` remains PASS by the reference document unless a later review finds a regression.

## Current cycle (roundup pause)

| Field | Value |
| --- | --- |
| Status | **typed-rpc-platform LANDED** — Grok PASS; PRs open but **CI not green** and **merge CONFLICTING/DIRTY** |
| Active worker | **None** — campaign rounded up for handover |
| Implementer | `composer-2.5`; reviewer `cursor-grok-4.6-xhigh`; no Fast/Cloud/Auto |
| Blockers | PR CI not scheduled/green; merge conflicts on both PRs. Tip + parallel ops **NOT PASS**. |
| Next step | Rchiemstra resolves PR conflicts + CI, then merges #17 then #53. Resume: unpark Tip, then parallel ops (see handover). |

### Composer 2.5 — static globs replace sync (2026-09-13, main)

| Change | Detail |
| --- | --- |
| `pyproject.toml` | Static `files` globs for `*_contract.py`, `tests/typecheck/*_protocol.py`, platform modules; **no** leaf/mutation paths, **no** `cad_mutation.py`, **no** `*_mutation.py` glob |
| Overrides | `follow_imports=normal` + `disallow_any_unimported` on `cad_methods_ops.*`, `parametric_ops.*`, contracts, protocols; `disallow_any_explicit` on ops/contracts; relax only `cad_dependencies`, `cad_mutation`, known untyped parametric siblings |
| Removed | `ci/sync_mypy_typed_slice.py`, DISCOVERED marker blocks, `test_pyproject_mypy_discovery_is_synced` drift gate |
| `ci/discover_typed_slice.py` | Discovery helpers only; `run_discovered_mypy()` = plain `uv run mypy --no-incremental` |
| Proof test | `test_discovered_leaf_with_any_fails_editor_mypy_without_pyproject_edits` — temp tree + static pyproject template, **no sync** |

**Tests re-run (Composer 2.5):**

| Lane | Result |
| --- | --- |
| `uv run mypy --no-incremental` | **0 errors, 8 entrypoint files** (leaves/mutations pulled via `follow_imports`) |
| `uv run python ci/qualify_body_create.py` | **228 passed** (−1: removed drift-sync test; no Body regression) |
| `tests/test_typed_platform_discovery.py` | **10 passed** (incl. Any-fail without sync) |
| `ci/run_contract_checks.py` | **OK** |
| `python -m compileall src tests ci addon` | **OK** |
| Native `--native` | Not re-run |

### Composer 2.5 — editor mypy fix (2026-09-13, main)

| Grok FAIL | Fix |
| --- | --- |
| Editor `uv run mypy` red / leaves omitted | `ci/sync_mypy_typed_slice.py` merges contract-paired paths + modules into `pyproject.toml` `# BEGIN:DISCOVERED_*` marker blocks; `run_discovered_mypy()` now uses synced pyproject (same as editor) |
| Proof | `uv run mypy --no-incremental` → **0 errors, 11 files**; temp dummy op with `Any` fails synced editor mypy; `test_pyproject_mypy_discovery_is_synced` drift gate |

**Tests:** focused **229**, Docker lint **OK**, native **16** (unchanged). Body did not regress.

## Independent Grok re-review — static globs (2026-09-14, `cursor-grok-4.6-xhigh`)

Overall: **PASS**. Composer’s static-glob claim holds. Do not trust Composer’s numbers; Grok re-ran the gates.

### Confirmations (do not trust)

| Check | Result |
| --- | --- |
| `uv run mypy --no-incremental` | **0 errors, 8 source files** |
| `uv run python ci/qualify_body_create.py` | **228 passed** (−1 removed drift-sync test, not Body) |
| `tests/test_typed_platform_discovery.py` | **10/10** |
| Dummy Any test | Writes `_STATIC_MYPY_PYPROJECT` under `tmp_path` only. **No** `sync_*`. **Does not** write production `pyproject.toml`. Production `uv run mypy` fails the dummy leaf `Any` via protocol import + `follow_imports=normal`. |
| New op, zero pyproject edits | Independent temp tree: contract + leaf + `{op}_mutation.py` + typecheck protocol. Leaf `Any` fails. `{op}_mutation.py` `Any` fails **when the leaf imports it** (Body pattern: `body_create` → `body_mutation`). Unused mutation `Any` is **not** followed (same as any unused file). |
| `cad_mutation.py` | **Not** in `files`. **No** `*_mutation.py` glob. Independent unused `cad_mutation.py` with `Any` is **not** typechecked. Relax override is defensive only. |
| Sync leftovers | `ci/sync_mypy_typed_slice.py` deleted. Repo grep: no `DISCOVERED` / `sync_pyproject` / `sync_mypy`. |

### Requirements 1–8

| # | Score | Evidence |
| --- | --- | --- |
| 1 | **PASS** | `commit_body_create_mutation` kept. One generic `commit_native_mutation` (native document, one admitted doc, apply+inspect bound). No `commit_body_set_tip_mutation`. `CadCollaborators` + `CompatibilityMutationAPI` expose the generic. |
| 2 | **PASS** | `sketch_public` still has legacy `body_set_tip` only. No new per-tool wrappers. Handlers from `TYPED_RPC_HANDLER` + `bind_typed_rpc_handlers` / facade `discover_typed_rpc_handlers`. |
| 3 | **PASS** | Directory/glob: `*_contract.py` + `tests/typecheck/*_protocol.py` + 8 platform entrypoints. Leaves **not** listed. `follow_imports=normal` + `disallow_any_explicit` on `cad_methods_ops.*` / `parametric_ops.*`. No per-op pyproject commit. |
| 4 | **PASS** | Woodpecker → `python ci/run_contract_checks.py` → `ci/check_*_contract.py`. Body check kept. |
| 5 | **PASS** | `generated/**` not dirty. |
| 6 | **PASS** | `body_create.py` +25 = `rpc_body_create` + `TYPED_RPC_HANDLER` (allowed discovery hook). `body_mutation.py` / contracts / `cad_mutation.py` internals untouched. |
| 7 | **PASS** | Later **new-named** ops add files only. No edit to collaboration_api / sketch_public / pyproject / Woodpecker / cad_methods. |
| 8 | **PASS** | Dummy Any test **runs** editor mypy (not path-string only). Failing `check_*_contract.py` **runs** and fails `run_contract_checks`. |

Body: **228**, not a regression vs 229. Native not re-run this cycle (Body native path unchanged; last Grok **16** stands).

**Leftover (not a platform FAIL):** converting the existing `parametric_ops.body_set_tip` file should drop that name from the Any-relax list (one pyproject edit when replacing a named legacy module). Brand-new op names do not touch pyproject.

**Next step:** Platform landed 2026-09-14. Orchestrator forks parallel op worktrees from parent `07d75f0497`, then unparks Tip. Tip stays **PARKED** until rebased onto landed SHA.

## Independent Grok re-review — editor-mypy sync (2026-09-13, `cursor-grok-4.6-xhigh`)

Overall: **NOT PASS**. Editor `uv run mypy --no-incremental` is **0 errors, 11 files** (prior red is fixed). Body qualify **229**. Scripted DISCOVERED marker sync is **not** an acceptable substitute for directory/glob: every later op still **rewrites and must commit** `pyproject.toml`. Parallel op worktrees will conflict on those blocks. Do not commit.

### Sync vs glob

`ci/sync_mypy_typed_slice.py` writes explicit leaf/mutation/client paths into three `# BEGIN:DISCOVERED_*` lists. Drift test `test_pyproject_mypy_discovery_is_synced` **requires** that commit. The dummy-`Any` test calls `sync_pyproject_mypy_typed_slice()` on the temp tree — it does **not** prove `uv run mypy` gates a new leaf without mutating pyproject.

A glob **can** work without per-op pyproject writes:

- Keep existing `*_contract.py` and `tests/typecheck/*_protocol.py` globs (new contracts/protocols already auto-included).
- `follow_imports = "normal"` + `disallow_any_explicit` on `addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.*` so a typecheck protocol import pulls the leaf and `{op}_mutation.py`.
- Relax `disallow_any_explicit` only for known untyped siblings (`cad_dependencies`; do not put `cad_mutation.py` in `files`).
- Same for `freecad_mcp.operations.parametric_ops.*` with exceptions for pre-existing untyped modules (`helpers`, spreadsheet/expression/sketch_attach, `body_set_tip` if still untyped). Do **not** glob `*_mutation.py` in `cad_methods_ops` (matches `cad_mutation.py`).

New ops then add files only. No sync. No pyproject commit.

### Per-requirement (1–8)

| # | Score | Evidence |
| --- | --- | --- |
| 1 | **PASS** | Body commit + one generic native commit unchanged. |
| 2 | **PASS** | Handler discovery on cad_methods/facade; no new per-tool methods in sketch_public. |
| 3 | **FAIL** | Editor mypy green (11 files) but **not** glob-only. Sync is a generated per-op file list in pyproject. Original requirement: directory/glob so new files are included **without** per-op pyproject edits. |
| 4 | **PASS** | Woodpecker still `run_contract_checks` → Body (qualify ran the same gate). |
| 5 | **PASS** | `generated/**` clean. |
| 6 | **PASS** | Body internals / `cad_mutation.py` not rewritten. |
| 7 | **PASS** for collaboration_api / sketch_public / cad_methods / Woodpecker (no per-op edits). **pyproject still serializes.** |
| 8 | **PASS** with asterisk | Tests invoke real mypy and a failing check script. Dummy `Any` only fails **after sync writes pyproject** — does not prove no-pyproject-edit gating. |

### Tests re-run (Grok)

| Lane | Result |
| --- | --- |
| `uv run mypy --no-incremental` | **0 errors, 11 files** |
| `uv run python ci/qualify_body_create.py` | **229 passed** |
| Native `--native` | Not re-run (editor/sync only; Body native path unchanged; last Grok 16 still stands) |
| Docker lint | Not re-run (qualify already ran `check_body_create_contract.py`) |

### Remaining Composer 2.5 fix (main only)

Remove DISCOVERED marker sync as the editor source of truth. Put **static globs + follow/Any overrides** (exceptions only for known untyped modules) in `pyproject.toml` so `uv run mypy --no-incremental` stays 0 on Body and a temp new leaf with `x: Any` fails **that same command without calling sync**. Delete or demote `sync_mypy_typed_slice.py` so later ops do not commit pyproject.

Do not commit. Do not unpark Tip.

### Composer 2.5 — typed-rpc-platform Grok fix pass (2026-09-13, main)

| Grok FAIL | Fix |
| --- | --- |
| #3 Mypy Any per-op pyproject | `run_discovered_mypy()` merges contract-driven modules into `disallow_any_explicit` + `follow_imports=normal` at CI time; test proves dummy `Any` on new leaf fails without pyproject edits |
| #7 `commit_native_mutation` not on injected APIs | Added to `CompatibilityMutationAPI` + `CadCollaborators` delegate |
| #7 RPC not live XML-RPC | `cad_methods.bind_typed_rpc_handlers(globals())`; `facade_bindings` loops `discover_typed_rpc_handlers()`; removed static `body_create` import/assign |
| #8 Discovery tests path-only | Tests run real `run_discovered_mypy()` (pass + fail) and failing `run_contract_checks.py` on temp fixtures |

**Tests (post-fix):** focused **227**, Docker lint **OK**, native **16**. Body did not regress.

**Remaining (honest):** Editor-only `python -m mypy` without CI discover merge may still miss new leaves until Grok confirms CI path is sufficient. Tip worktree untouched.

## Independent Grok re-review — typed-rpc-platform after four fixes (2026-09-13, `cursor-grok-4.6-xhigh`)

Overall: **NOT PASS**. Parent `d0d82b743886` / MCP `b32a13422a9d` still dirty. Tip not edited. Prior FAILs #7 and #8 are fixed. CI Any-discover works. **Body editor mypy regresses** (`uv run mypy` 2 errors, 8 files). Do not commit.

### Prior FAILs

| Prior FAIL | Result |
| --- | --- |
| CI `run_discovered_mypy` bans `Any` on new leaf | **Fixed for CI.** Dummy leaf `from typing import Any; value: Any = 1` fails `run_discovered_mypy` on a temp tree; clean dummy passes. Merged config includes `body_create` / `body_mutation` / `body_ops` in `disallow_any_explicit`. Body still in discovered **11** files. |
| `commit_native_mutation` not on injected APIs | **Fixed.** `CompatibilityMutationAPI` + `CadCollaborators` delegate. Mutation module can call `collaborators.commit_native_mutation(...)` without editing `collaboration_api.py` / `cad_dependencies.py` per op. |
| RPC not live XML-RPC | **Fixed.** `cad_methods.bind_typed_rpc_handlers(globals())`; `facade_bindings` loops `discover_typed_rpc_handlers()`; static `body_create` import/assign removed. Tests: `cad_methods.body_create is handler`; `bind_freecad_rpc` publishes `body_create`. JSON-RPC contract still in focused 227. |
| Discovery tests path-only | **Fixed.** 9 tests invoke real `run_discovered_mypy` (pass+fail) and `run_contract_checks.py` against a temp `check_*` that exits 1. Grok re-ran: **9 passed**. |

### Per-requirement (1–8)

| # | Requirement | Score | Evidence |
| --- | --- | --- | --- |
| 1 | Keep Body commit; one generic native commit; no per-op methods | **PASS** | Unchanged from prior PASS. No `commit_body_set_tip_mutation`. |
| 2 | Discover handlers; no new per-tool methods | **PASS** | Discovery now on `cad_methods` / facade (better for XML-RPC). `sketch_public` has no new per-tool method and no `body_create` wrapper. |
| 3 | pyproject glob mypy; Keep Body; no Any | **FAIL** | **CI path OK** (11 files, dummy `Any` fails). **Editor path red:** `uv run mypy --no-incremental` → **2 errors, 8 files**. `files` still omit leaf/mutation/client; `follow_imports=skip` so `body_create_protocol.py` sees `body_create_operation` as `Any` and an unused `type: ignore`. New leaves are not editor-gated. This is a Body editor-gate regression vs the reference (`uv run mypy` used the same rules as CI). |
| 4 | Woodpecker discover runner; keep Body | **PASS** | Docker: `check_body_create_contract.py`, `OK (1 gate(s))`. |
| 5 | No `generated/**` | **PASS** | Clean. |
| 6 | No Body internals rewrite | **PASS** | `cad_mutation.py` / contracts / `body_mutation.py` internals untouched. `body_create.py` still only the discovery hook. |
| 7 | Later ops only add new files | **PASS** | No per-op edit of collaboration_api / sketch_public / pyproject / Woodpecker / cad_methods / addon facade / cad_dependencies. Allowed later files: contracts, leaf, `{op}_mutation.py`, `parametric_ops/{op}.py`, `ci/qualify_*` + `check_*`, tests, typecheck protocol. |
| 8 | Prove new op gated without pyproject/Woodpecker edits | **PASS** | Real mypy + failing check-script tests (not glob strings). |

### Tests re-run (Grok)

| Lane | Result |
| --- | --- |
| `uv run python ci/qualify_body_create.py` | **227 passed** (mypy 11 files). No Body CI regression. |
| Docker Woodpecker `python:3.12` | **OK** |
| `--native` `freecad-ci-mcp:24.04-phase1` + `build_docker` | **16 passed** (5.57s) |
| `tests/test_typed_platform_discovery.py` | **9 passed** |
| Editor `uv run mypy --no-incremental` | **FAIL** 2 errors, 8 files |

### Remaining Composer 2.5 fix (main only)

1. **`uv run mypy` must be green and Any-strict on contract-paired leaves** without per-op pyproject lists. CI `run_discovered_mypy` is not enough: the Body reference editor gate is `pyproject.toml` / `uv run mypy`. Restore `follow_imports=normal` + `disallow_any_explicit` for paired leaf/mutation/client via **globs** (e.g. typed `cad_methods_ops` leaves imported from `tests/typecheck/*_protocol.py`, `parametric_ops.*`, `*_mutation`) or sync `files` from discover. Prove: `uv run mypy --no-incremental` exits 0; a new `*_protocol.py` importing a leaf with `x: Any` fails that same command without editing pyproject.

Honest leftovers (not this FAIL): MCP catalog still needs subject `manifest.py` + generated regen for a new tool name; `CadCollaborators.__post_init__` now requires `commit_native_mutation` on every injected API (Body qualify mocks that use `CollaborationAPI` are fine; some phase15 cad doubles outside this lane are not).

Do not commit. Do not unpark Tip.

### Composer 2.5 — typed-rpc-platform (2026-09-13, main checkout)

Shared infrastructure only (no `commit_body_set_tip_mutation`, no Tip Woodpecker lines, no Tip pyproject file lists).

| Area | What landed |
| --- | --- |
| Generic native commit | `CollaborationAPI._resolve_admitted_document` + `commit_native_mutation` (apply+inspect on one admitted document; `_NativeMutationDocument` Protocol; no per-op commit methods). `commit_body_create_mutation` unchanged in policy. |
| RPC discovery | `typed_rpc_discovery.py` scans `cad_methods_ops` siblings for `TYPED_RPC_HANDLER`; `body_create.py` registers `rpc_body_create`; `sketch_public.py` exports discovered handlers (no per-op functions added there for Body). |
| Mypy glob + discover | `pyproject.toml` globs `*_contract.py`, `*_protocol.py`; `ci/discover_typed_slice.discover_typed_mypy_files` pairs contracts → leaf, `{op}_mutation` / `body_mutation`, client op (`body_ops` exception). |
| Woodpecker discover | `ci/run_contract_checks.py` runs every `ci/check_*_contract.py`; parent `ci/woodpecker/freecad-mcp-lint.sh` calls it. |
| Discovery proof | `tests/test_typed_platform_discovery.py` temp fixture: dummy `check_dummy_op_contract.py` + contract/leaf/mutation/client/typecheck files discovered without editing pyproject/Woodpecker. |

**Platform files changed (parent + MCP, uncommitted):**

- Parent: `ci/woodpecker/freecad-mcp-lint.sh`
- MCP new: `ci/discover_typed_slice.py`, `ci/run_contract_checks.py`, `addon/.../typed_rpc_discovery.py`, `tests/test_typed_platform_discovery.py`
- MCP modified: `collaboration_api.py`, `body_create.py`, `sketch_public.py`, `pyproject.toml`, `ci/check_body_create_contract.py`, `ci/qualify_body_create.py`, `tests/test_body_create_contract_gate.py`, `tests/test_phase15_sketch_injection.py`

**Tests (Composer, main MCP worktree):**

| Lane | Command | Result |
| --- | --- | --- |
| Body focused | `uv run python ci/qualify_body_create.py` | **222 passed** (was 218; +4 discovery tests; Body did not regress) |
| Woodpecker lint | `docker run --rm -v D:/code/FreeCAD:/work -w /work python:3.12 sh ci/woodpecker/freecad-mcp-lint.sh` | **OK** (`run_contract_checks` → `check_body_create_contract.py`) |
| Body `--native` | `freecad-ci-mcp:24.04-phase1` + `build_docker` via `FreeCADCmd` (`LD_LIBRARY_PATH=/build/lib:/build/Mod/Part:/build/Mod/Material:/build/Mod/Materials`) | **16 passed** |

Tip worktree `D:/code/FreeCAD-wt-body-set-tip`: **untouched by this pass** (still dirty/unmerged, **PARKED NOT PASS**).

## Independent Grok review — typed-rpc-platform (2026-09-13, `cursor-grok-4.6-xhigh`)

Overall: **NOT PASS**. Parent HEAD `d0d82b743886`, MCP HEAD `b32a13422a9d`, both dirty with uncommitted platform. Tip worktree not edited. Composer’s Body/lint/native numbers **reproduced**; requirements 3, 7, and 8 fail. Do not claim platform PASS.

### Per-requirement

| # | Requirement | Score | Evidence |
| --- | --- | --- | --- |
| 1 | `commit_body_create_mutation` kept; one generic native commit; no per-op methods | **PASS** | `commit_body_create_mutation` still requires `_NativeBodyDocument`, one `_resolve_admitted_document`, apply+inspect close over that object, no `_commit_without_native`. `commit_native_mutation` is the only generic (`_NativeMutationDocument`, same one-document bind). No `commit_body_set_tip_mutation`. |
| 2 | `sketch_public.py` discovers handlers; no new per-tool methods | **PASS** | `export_typed_rpc_handlers(globals(), discover_typed_rpc_handlers())`. `body_create` comes from `TYPED_RPC_HANDLER` in the leaf. No new per-tool function added here (`body_set_tip` is the pre-existing legacy GUI wrapper). |
| 3 | pyproject glob mypy includes new contracts/leaves/mutation/typecheck; Keep Body; no Any | **FAIL** | `files` globs only `*_contract.py` and `tests/typecheck/*_protocol.py`. Body leaf/mutation/client **dropped** from `files` (`body_create.py`, `body_mutation.py`, `body_ops.py`). They return in CI only via `discover_typed_mypy_files` (Grok listed 11 files; Body still among them). `disallow_any_explicit` / `follow_imports=normal` overrides still name Body modules only. Global `follow_imports=skip` + `strict` does **not** enable `disallow_any_explicit`. A new leaf `x: Any` is not a mypy error without a pyproject edit. |
| 4 | Woodpecker one discover runner; keep Body check | **PASS** | Parent `ci/woodpecker/freecad-mcp-lint.sh` calls `python ci/run_contract_checks.py`. Docker log: `check_body_create_contract.py` then `OK (1 gate(s))`. |
| 5 | Do not hand-edit/regen `generated/**` | **PASS** | `git status` clean under `src/freecad_mcp/generated` and `addon/FreeCADMCP/generated`. |
| 6 | No internals rewrite of Body create/contract/mutation; prefer not to edit `cad_mutation.py` | **PASS** | `cad_mutation.py`, `body_create_contract.py`, `body_mutation.py` untouched. `body_create.py` diff is only `_BodyCreateRpcFacade` + `rpc_body_create` + `TYPED_RPC_HANDLER` (move of the old `sketch_public.body_create` wrapper). Apply/inspect/run unchanged. **Legitimate discovery hook**, not a forbidden internals rewrite. |
| 7 | Later ops only add new files; no edits to collaboration_api / sketch_public / pyproject / Woodpecker | **FAIL** | Generic commit is **not** on `CadCollaborators` or `CompatibilityMutationAPI` — a Body-style `collaborators.commit_native_mutation(...)` is an AttributeError unless `cad_dependencies.py` / `collaboration_dependencies.py` are edited. `cad_methods.py` still statically imports `body_create`; `facade_bindings.py` still assigns `FreeCADRPC.body_create`. Discovery into `sketch_public.globals()` does not publish XML-RPC. pyproject Any overrides still require per-op edits (see #3). |
| 8 | Prove a new op file is gated without editing pyproject/Woodpecker | **FAIL** | `tests/test_typed_platform_discovery.py` temp trees only assert **path strings** from `discover_typed_mypy_files` / `discover_contract_check_scripts`. They do not run mypy on the dummy files, do not execute `run_contract_checks.py` against a temp failing `check_dummy_op_contract.py`, and do not prove `disallow_any_explicit`. `test_run_contract_checks_runs_production_gates` only re-runs the production Body gate. |

### Files vs “no internals rewrite” / “no per-op methods”

- **No per-op commit methods** added (`commit_body_set_tip_mutation` absent).
- **No forbidden Body internals rewrite.** `body_create.py` handler export is allowed as a discovery hook.
- Remaining per-op lists (not new methods, but still serialize later ops): `pyproject.toml` mypy overrides; `cad_methods.py` imports; `rpc_server_ops/facade_bindings.py` assignments.

### Tests re-run (Grok, main MCP worktree)

| Lane | Command | Result |
| --- | --- | --- |
| Body focused | `uv run python ci/qualify_body_create.py` | **222 passed** (mypy 11 files + architecture; includes +4 discovery tests). No Body regression vs 218. |
| Woodpecker lint | `docker run --rm -v D:/code/FreeCAD:/work -w /work python:3.12 sh ci/woodpecker/freecad-mcp-lint.sh` | **OK** (`run_contract_checks` → `ci/check_body_create_contract.py`, 1 gate) |
| Body `--native` | `python3 ci/qualify_body_create.py --native` in `freecad-ci-mcp:24.04-phase1` + host `build_docker` (`LD_LIBRARY_PATH` = unique dirs of `*.so` under `/build`; `PYTHONPATH` = MCP + `/build/lib:/build/Mod`) | **16 passed** in 6.56s. Historically stable Body lane; not rubber-stamped from Composer. |

### Composer 2.5 required fixes (main checkout only; no worktrees)

1. **Mypy Any gate must auto-cover new leaves/mutations/client ops** without editing `pyproject.toml`. Glob (or discover-driven) `disallow_any_explicit` + `follow_imports=normal` for paired typed modules. Put leaves/mutations on the editor `files` surface or prove `python -m mypy` with pyproject alone typechecks them. Keep Body in the 11-file set.
2. **Expose `commit_native_mutation` on `CompatibilityMutationAPI` and `CadCollaborators`** (same shape as `commit_body_create_mutation`: require native, one admitted document, apply+inspect bound). Later mutation modules must not edit `collaboration_api.py` *or* `cad_dependencies.py`.
3. **Bind discovered `TYPED_RPC_HANDLER`s onto `FreeCADRPC`** (and `cad_methods` export) so a new leaf registration is a live RPC method without editing `cad_methods.py` / `facade_bindings.py` / `sketch_public.py`.
4. **Replace glob-string tests with real gates:** temp dummy op with `Any` must fail mypy; temp `ci/check_dummy_op_contract.py` that exits 1 must make `run_contract_checks.py` fail; both without changing pyproject/Woodpecker. Assert `cad_mutation.py` stays undiscovered.

Do not commit. Do not unpark Tip.

## Grok re-review — `body_set_tip` after Composer fixes (2026-09-13, `cursor-grok-4.6-xhigh`)

Overall: **NOT PASS**. Main HEADs unchanged (`d0d82b743886` / `b32a13422a9d`). Area 5 (read-only inspect) is accepted. Native matrix cases exist but the `--native` suite is **not deterministic**.

### Prior FAILs

| Prior FAIL | Result |
| --- | --- |
| Area 5 writable Tip on inspect | **Fixed.** `TipBodyReadObject` has Tip getter only; `TipBodyWriteObject` has setter; `TipReadDocument.getObject` → read object. `postcondition_surface_is_read_only` uses `body.Tip = body  # type: ignore[misc]`. `warn_unused_ignores = true` + mypy 17 files passed ⇒ assignment is a type error without ignore. Vendored contracts identical (SHA-256 `B7B09821…`). |
| Native Busy / empty Pad | **Fixed as fixture.** `_make_idle_body_with_pad_and_pocket` uses closed circles, Pad+Pocket, `_assert_document_idle`, Tip starts at Pad, mutation target is Pocket. `RecomputeProbe` present. Success path no longer Busy. |
| Native matrix missing | **Cases present** (validation/apply/recompute/inspection rollback, rollback-failure fence, postcondition cannot write, rich-model 4 stages, missing targets). **Not proven:** suite flaked when Grok re-ran it. |

### 14 vs Body 16

Missing Body-lane tests (not Tip mutation cases):

1. `test_branch_built_freecad_exposes_the_frozen_collaboration_api`
2. `test_typed_cad_adapter_publishes_one_exact_structural_revision_event` (`cad_mutation` / `create_object`)

77 native collab/binding tests not re-run (C++ unchanged). Those two gaps are N/A for Tip. They are **not** why this re-review is NOT PASS.

### Per-area scores

| # | Area | Score | Evidence |
| --- | --- | --- | --- |
| 1 | Native recompute before inspection | PASS | Unchanged production policy; success test uses RecomputeProbe + Pad→Pocket |
| 2 | Native capability required | PASS | Unchanged; capability unit test still in focused 161 |
| 3 | Exact admitted document | PASS | Unchanged one-lookup + identity check |
| 4 | Strict public success shape | PASS | Unchanged contract; focused 161 |
| 5 | MCP static contract | PASS | Protocol split + unused-ignore + identical vendors + no typed-slice `Any` |
| 6 | Editor/CI mypy | PASS | Docker lint re-run OK after contract change |
| 7 | Public JSON-RPC / MCP dispatch | PASS | Focused 161 includes memory-session tests |
| 8 | Native qualification matrix | FAIL | Matrix **code** is present. Grok `--native` ×3: **13/14**, **14/14**, **13/14**. Failures: `rich_model[apply]` (Body OutList / state), then `validation_failure_restores_complete_state` (`ExistingAnchor` FeaturePython / Proxy in `_model_state`). Isolation run of rich-model 4/4 passed. Composer “14 passed” is a single lucky run. |
| 9 | Deliberately broken variants | PASS | Focused 161 still fails TIP007 / TIP015 mutants |
| 10 | Committed/unknown | PASS | Unchanged parser/JSON-RPC tests in 161 |

### Commands re-run this pass

| Lane | Result |
| --- | --- |
| `uv run python ci/qualify_body_set_tip.py` | **161 passed** |
| `uv run python ci/qualify_body_create.py` | **218 passed** |
| Docker Woodpecker `python:3.12` lint | **OK** |
| `--native` run 1 | **FAIL 1** `rich_model[apply]` |
| `--native` run 2 | **14 passed** |
| `--native` isolated `rich_model` | **4 passed** |
| `--native` run 3 | **FAIL 1** `validation_failure_restores_complete_state` |

### Remaining Composer 2.5 defects (same worktree)

1. `tests/test_native_body_set_tip.py::_model_state` — `id(item.Proxy)` for FeaturePython is not stable across rollback/recompute. Validation flake differed on `ExistingAnchor` Proxy/content.
2. Native suite isolation — first full run failed `rich_model[apply]` (Body OutList showed duplicate `Pad`); same test passed alone and on a later full run. Likely leftover collaboration/document state after `rollback_failure` fence tests.
3. Do not claim `--native` 14 passed from one run. Require 3 consecutive green full-suite runs in `freecad-ci-mcp:24.04-phase1`.

## Independent Grok review — `body_set_tip` (2026-09-13, `cursor-grok-4.6-xhigh`)

Overall: **NOT PASS**. Main checkout HEADs unchanged (`d0d82b743886` / `b32a13422a9d`). Reviewer re-ran focused Tip, Body regression, Woodpecker lint, and native `--native` (runtime **present**; Composer skip was incorrect).

### Per-area scores

| # | Acceptance area | Score | Evidence |
| --- | --- | --- | --- |
| 1 | Native recompute before inspection | PASS | `apply_body_set_tip` / `read_body_set_tip_result` do not recompute or transact; `run_body_set_tip_native_mutation` owns orchestration; adapter test event order `apply → recompute → inspect → validate → commit`; architecture TIP001; `features_gui.body_set_tip_gui` no longer leaf-recomputes and is unused by the typed RPC path |
| 2 | Native capability required before apply | PASS | `commit_body_set_tip_mutation` `isinstance(..., _NativeBodyDocument)` before callback; no `_commit_without_native`; `test_native_capability_is_required_before_tip_apply` |
| 3 | Exact admitted document | PASS | One `_resolve_admitted_document` in the Tip commit; apply+inspect receive the same object (`state.document is not document` → `DOCUMENT_IDENTITY_MISMATCH`); TIP005. Shared helper extract does not change `commit_body_create_mutation` policy |
| 4 | Strict public success shape | PASS | Versioned TypedDict; `make_body_set_tip_success` only after native `True`; parser + discriminant product tests |
| 5 | MCP static contract (no Any; vendored identity; mypy) | FAIL | Vendored contracts byte-identical (SHA-256 `AC00F3B8…`); no `Any` on Tip typed modules; mypy 17 files OK. **Defect:** `TipReadDocument.getObject` returns writable `TipBodyObject` (Tip setter). `tests/typecheck/body_set_tip_protocol.py::postcondition_surface_is_read_only` assigns `body.Tip` **without** `type: ignore`, so writes through the inspect surface are allowed. body_create rejects Label/addObject writes |
| 6 | Automatic editor/CI mypy gate | PASS | Tip files in `pyproject.toml` `files` + `disallow_any_explicit`; Woodpecker calls `ci/check_body_set_tip_contract.py`. Re-ran Docker `python:3.12` lint: OK |
| 7 | Public JSON-RPC / real MCP schema dispatch | PASS | `tests/test_body_set_tip_json_rpc_contract.py` uses MCP memory session `list_tools`/`call_tool`; HTTP transport only; non-strings never reach JSON-RPC; MCP tool calls `freecad.body_set_tip()` |
| 8 | Native qualification matrix / rollback | FAIL | Runtime **exists** (`freecad-ci-mcp:24.04-phase1` + `D:/code/FreeCAD/build_docker` `libFreeCADApp.so`). Grok ran `--native`: **1 failed**. Fixture uses empty Pad → pending recompute → `Busy`. No apply/recompute/inspection/validation rollback matrix (body_create native is 16 tests). Production **can** succeed on an idle valid Body (reviewer probe only; not a committed test) |
| 9 | Deliberately broken variants incl. CI path | PASS | Gate tests fail TIP007 cached success after native rejection and TIP015 omitted postcondition; `test_native_rejection_never_returns_cached_success` |
| 10 | Committed/unknown; no cached success; malformed committed | PASS | Parser unknown/non-object → uncertain `committed=None`; malformed committed retains `committed=true` (JSON-RPC test); native Busy is proven rejection not cached success |

### Extra checks

- MCP path is typed JSON-RPC (`body_set_tip_operation` → `freecad.body_set_tip()`), not execute-code. Legacy template lives in `body_set_tip_legacy.py` (outside mypy slice).
- `body_create.py` / `body_create_contract.py` / `body_mutation.py` internals not rewritten. `cad_mutation.py` untouched. `src/freecad_mcp/generated/**` not hand-edited.
- Public args remain `doc_name`, `body_name`, `feature_name`.
- `collaboration_api.commit_body_create_mutation` policy unchanged (lookup extracted to `_resolve_admitted_document`; Body 218 still passed).
- Typed-slice `Any`: none. `tests/test_body_set_tip.py` imports `Any` (not in mypy `files`).

### Commands re-run (Grok)

| Lane | Command | Result |
| --- | --- | --- |
| Tip focused | `uv run python ci/qualify_body_set_tip.py` (MCP worktree) | **161 passed** (mypy 17 files + pytest) |
| Body regression | `uv run python ci/qualify_body_create.py` (MCP worktree) | **218 passed** |
| Woodpecker lint | `docker run --rm -v D:/code/FreeCAD-wt-body-set-tip:/work -w /work python:3.12 sh ci/woodpecker/freecad-mcp-lint.sh` | **OK** (`check_body_create_contract.py` + `check_body_set_tip_contract.py`) |
| Native Tip | `python3 ci/qualify_body_set_tip.py --native` in `freecad-ci-mcp:24.04-phase1` with `build_docker` libs | **FAIL 1/1** `Busy`: `document has pending recompute work outside the prepared operation` |

Native blocker: **not missing runtime**. Runtime present; committed native test is wrong. Do not skip-as-pass.

### Composer 2.5 required fixes (do not implement here)

1. `tests/test_native_body_set_tip.py::test_body_set_tip_native_success_inspects_after_recompute` — use a **valid idle** Body (closed sketch geometry + Pad; all `Up-to-date` / `MustExecute False` after `recompute`). Empty Pad stays pending → `Busy`. Copy `RecomputeProbe` from `test_body_create_native_success_inspects_after_recompute`. Change Tip between two valid PartDesign features (Pad/Pocket), not Sketch (`RecomputeFailed`: linked object is not a PartDesign feature).
2. Expand `--native` to the body_create matrix (validation/apply/recompute/inspection rollback, rollback-failure uncertain+fence, postcondition cannot write, rich-model restore) in `tests/test_native_body_set_tip.py` or equivalent.
3. `src`+addon `body_set_tip_contract.py` + `tests/typecheck/body_set_tip_protocol.py` — split read-only Tip object (getter only) vs apply setter; `TipReadDocument.getObject` must not allow `body.Tip = ...`; add `# type: ignore[misc]` negative example like body_create Label.

### Next step

Grok re-review after Composer fixes below. **Do not commit. Do not start `sketch_create`. Do not claim PASS.**

## Composer 2.5 fixes after Grok review (2026-09-13)

Addressed all three required fixes in worktree `D:/code/FreeCAD-wt-body-set-tip/tools/mcp/freecad-mcp` (uncommitted).

| Fix | Files | What changed |
| --- | --- | --- |
| 1. Native success fixture | `tests/test_native_body_set_tip.py` | `_make_idle_body_with_pad_and_pocket`: closed circle sketch + Pad + Pocket, `_assert_document_idle`, initial Tip=Pad; success test changes Tip Pad→Pocket with `RecomputeProbe` + phase order `apply → recompute → inspect → validate` |
| 2. Native qualification matrix | `tests/test_native_body_set_tip.py` | Ported body_create native tests: validation/apply/recompute/inspection rollback, rollback-failure uncertain+fence, postcondition cannot write, rich-model restore (4 stages), isolated failure recovery, missing-target typed errors |
| 3. Read vs write Tip protocols | `src/freecad_mcp/_shared/protocol/body_set_tip_contract.py`, `addon/FreeCADMCP/_shared/protocol/body_set_tip_contract.py`, `body_set_tip.py`, `tests/typecheck/body_set_tip_protocol.py` | Split `TipBodyReadObject` (getter only) vs `TipBodyWriteObject` (setter); `TipReadDocument.getObject` → read type; `TipBodyDocument.getObject` → write type; postcondition negative example uses `# type: ignore[misc]` on `body.Tip = …` |

### Test evidence (Composer, post-fix)

| Lane | Command | Result |
| --- | --- | --- |
| Tip focused | `uv run python ci/qualify_body_set_tip.py` | **161 passed** (mypy 17 files + pytest) |
| Body regression | `uv run python ci/qualify_body_create.py` | **218 passed** |
| Woodpecker lint | `docker run --rm -v D:/code/FreeCAD-wt-body-set-tip:/work -w /work python:3.12 sh ci/woodpecker/freecad-mcp-lint.sh` | **OK** |
| Native Tip | `python3 ci/qualify_body_set_tip.py --native` in `freecad-ci-mcp:24.04-phase1` + host `D:/code/FreeCAD/build_docker` libs mounted at `/build` | **14 passed** (was Grok FAIL 1/1 `Busy`) |

Main checkout HEADs unchanged: parent `d0d82b743886`, MCP gitdir `b32a13422a9d`.

Honest limitations: Composer did not re-run full `test_native_collaboration_api.py` (77-test collaboration lane). Native count is 14 (Tip-only file) vs body_create reference 16 in shared collaboration file — Grok should confirm parity. No commit/PR.

## Inventory counts (source of truth)

Generated registrations declare **171** tools (`src/freecad_mcp/generated/capabilities/registration.py` comment `tool count: 171`). Subject manifests parse to the same 171 names. Generated `@mcp.tool()` count is 171. Manifest ↔ generated name sets match.

| Kind (inventory) | Count | Manifest `MutationClass` notes |
| --- | --- | --- |
| mutation | 107 | CAD/document modelling writes that should follow `body_create` |
| read | 36 | `MutationClass.READ` minus GUI reads |
| lease-control | 9 | `MutationClass.LEASE` (9) |
| execute-escape | 3 | `execute_code`, `execute_code_async`, `run_transaction` |
| gui | 13 | view/selection/color tools |
| other | 3 | request/worker control (`cancel_request`, `claim_acquisition_result`, `cancel_worker_job`) |
| **Total** | **171** | Manifest raw: MUTATION 117, READ 42, LEASE 9, EXECUTION 3 |

Manifest `execution_mode` is `TYPED_GATEWAY` for 170/171 tools; only `execute_code` is `GENERATED_SCRIPT`. **That label is not reality:** most MCP operations still send generated Python through `execute_code`.

### Review verdict

| Status | Count | Meaning |
| --- | --- | --- |
| PASS | 1 | `body_create` only (reference; not re-qualified this pass) |
| FAIL | 106 | CAD/document mutations that do not meet the acceptance table |
| N/A-readonly | 36 | Reads; native transaction matrix N/A |
| N/A-lease | 9 | Lease tools; not CAD typed-RPC |
| N/A-gui | 13 | View/selection/color |
| N/A-escape | 3 | execute-code escape hatches |
| N/A-runtime | 3 | Request/worker control |

Native transaction requirements apply to **mutations** (`native_txn=yes` in the registry). They do not apply to reads/lease/gui/escape/runtime.

### Stale names (removed from registry)

Live Cursor `user-freecad` namespace listed tools **not** in generated 171. Do not assign Composer worktrees for them:

| Name | Finding |
| --- | --- |
| `save_document_copy` | No manifest, no `@mcp.tool()`, no MCP source hit. Stale. |
| `get_mutation_readiness` | No manifest, no `@mcp.tool()`, no MCP source hit. Stale. |

Exported but **not** MCP tools (no `@mcp.tool()`): `force_release_stale_lock`, `heartbeat_document_lock` (both stub/removed shims).

## `body_create` PASS evidence (from reference; do not re-qualify unless regression)

Public args remain `doc_name`, `body_name`. Native FreeCAD owns transaction, final recompute, read-only postcondition interval, and rollback.

| Acceptance area | Result | Evidence (reference 2026-09-13) |
| --- | --- | --- |
| Native recompute before inspection | PASS | Native phase-order test; postflight writes rejected and rolled back |
| Native capability required | PASS | Bridge refuses documents without native postcondition API before apply |
| Exact admitted document | PASS | One lookup; native apply and inspection receive the same object |
| Strict public success shape | PASS | Version/boolean checks, required fields, contradictory error, rollback, native-status |
| MCP static contract | PASS | Public client re-export + concrete MCP return followed by mypy; Body modules reject explicit and unfollowed-import `Any`; vendored contract identity gated |
| Automatic editor/CI mypy gate | PASS | `pyproject.toml` default targets + per-module strictness; Woodpecker lint runs the same gate |
| Public JSON-RPC contract | PASS | Real MCP memory session initializes, discovers schema, calls the tool; invalid types never reach JSON-RPC |
| Native qualification matrix | PASS | Apply/recompute/inspection/validation failures restore listed native state; rollback failure remains uncertain and fences later mutations |
| Deliberately broken variants | PASS | Mutants for cached success after native rejection and omitted postcondition fail the behavioral gate |
| Committed/unknown response outcome | PASS | Unknown objects, non-objects, transport failures, GUI timeouts remain uncertain; malformed committed results retain `committed=true` and prohibit replay |

Lanes: focused **218**, native **16**, collaboration/binding **77**. Ruff + architecture/type gate. Parent Woodpecker `ci/woodpecker/freecad-mcp-lint.sh` passed in clean `python:3.12`. Native C++ SHA-256 in the reference doc. These qualify this slice, not the whole FreeCAD suite.

Implementation boundaries (keep as template):

1. `addon/.../cad_methods_ops/body_create.py` — validate, create, record identity; inspect; **no** transaction/recompute
2. `addon/.../cad_methods_ops/body_mutation.py` — fixed orchestration; apply/inspection errors provisional until recognized native rollback
3. `addon/FreeCADMCP/collaboration_api.py` — one document, native capability, bind both callbacks
4. `src/freecad_mcp/_shared/protocol/body_create_contract.py` (+ vendored addon copy must be identical)
5. `src/freecad_mcp/operations/parametric_ops/body_ops.py` — typed request, parse, concrete `CallToolResult`

Reference: “The legacy Body Tip implementation lives separately.”

## Shared FAIL gap vs `body_create` (all FAIL mutations)

| Acceptance area | body_create | All other CAD/document mutations |
| --- | --- | --- |
| Native recompute before inspection | PASS | FAIL — templates/GUI leaves call `doc.recompute()`; `run_cad_mutation` defaults to legacy leaf-owned recompute (`native_recompute=False`) |
| Native capability required | PASS | FAIL — `require_native` default false; execute-code path has no `commitCompatibilityMutation` check |
| Exact admitted document | PASS | FAIL — `getDocument(name)` by string; `bind_document` default false on cad_mutation |
| Strict public success shape | PASS | FAIL — ad-hoc `{ok}`, `{success}`, raw strings; no versioned TypedDict / vendored contract |
| MCP static contract (no Any; vendored identity) | PASS | FAIL — Body mypy slice only; several generated tools still annotate `Any`; no per-op vendored contract |
| Automatic editor/CI mypy gate | PASS | FAIL — `pyproject.toml` `files` list is Body-only; Woodpecker runs `ci/check_body_create_contract.py` only |
| Public JSON-RPC contract (real MCP schema dispatch) | PASS | FAIL — many MCP tools never call the addon RPC method; they `execute_code` generated Python. No `qualify_<op>.py` MCP memory-session tests |
| Native qualification matrix / rollback | PASS | FAIL — only `ci/qualify_body_create.py --native` exists |
| Deliberately broken variants including CI failure path | PASS | FAIL — Body mutants only |
| Committed/unknown response outcome | PASS | FAIL — templates print success JSON; transport loss is not a versioned uncertain result; cad_mutation can restore a historical envelope after native rejection |

Additional systemic defects:

1. **MCP tool ≠ addon RPC.** For `body_set_tip`, `sketch_create`, `pad_feature`, `pocket_feature`, spreadsheets, etc., the MCP operation renders templates and calls `execute_code` even though `FreeCADConnection` / addon JSON-RPC methods exist. Agents hitting MCP never exercise the typed RPC path.
2. **`run_cad_mutation` is not `body_mutation`.** Production callers never pass `native_recompute=True` or `require_native=True`. Legacy path recomputes inside the apply callback (`cad_mutation._recompute_native_callback` / GUI `doc.recompute()`).
3. **`collaboration_api.commit_compatibility_mutation` uses `Any`** and can commit without native (`_commit_without_native`) unless `require_native`. `commit_body_create_mutation` is the strict Body-only API.
4. **Mypy/CI gate is Body-scoped.** `pyproject.toml` `files` and Woodpecker `python ci/check_body_create_contract.py` will not catch other operations until each slice is added (sequential on those files).
5. **Only one `qualify_*.py`:** `ci/qualify_body_create.py`.
6. **Generated `Any`** on public MCP signatures: `sketch_attach`, `sketch_add_geometry`, `sketch_add_constraint`, `create_object`, `edit_object`, `repair_references`, `spreadsheet_set_cells`, `spreadsheet_get_cells`, plus several GUI/assembly tools.

`cad_mutation.py` itself uses `Any` throughout; it is a shared sequential choke point if a Composer worktree “upgrades” the adapter instead of adding a per-op mutation module like `body_mutation.py`.

## `body_set_tip` (Composer slice; Grok **NOT PASS**)

Typed JSON-RPC implementation exists in the worktree and is **not** the old execute-code MCP path. Overall still **NOT PASS** (native test FAIL + inspect protocol allows Tip writes). See Independent Grok review section above for per-area scores.

## Overlap groups

Shared choke files for **every** CAD mutation worktree (treat as sequential vs `body_create` and vs each other if edited):

- `addon/FreeCADMCP/collaboration_api.py`
- `addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/cad_mutation.py` (legacy shared adapter; prefer **not** editing — add a per-op module like `body_mutation.py`)
- `addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/sketch_public.py` (PartDesign cluster dispatch)
- `src/freecad_mcp/generated/capabilities/**` — regenerate, do not hand-edit
- `src/freecad_mcp/capabilities/<subject>/manifest.py` (then regenerate)
- `pyproject.toml` (mypy `files` + overrides)
- `ci/qualify_*.py`, `ci/check_*_contract.py`
- Parent `ci/woodpecker/freecad-mcp-lint.sh`

| Group | N | Parallel? | Shared files / notes | Members (sample) |
| --- | --- | --- | --- | --- |
| G-advanced-diagnostics | 16 | sequential if touching shared CI/collaboration/generated | snapshot/restore/relink/capture/FEM/run_transaction/diagnoses. Mixed execute-code and typed RPC (snapshot/restore/run_fem_analysis). | `audit_hardcoded_dimensions`, `capture_state`, `compare_documents`, `diagnose_helix`, `diagnose_parametric`, `diagnose_pocket`, `geometric_diff`, `get_dependency_graph`, `get_sketch_diagnostics`, `inspect_geometry`, `match_subshape`, `relink_references`… |
| G-assembly | 4 | sequential if touching shared CI/collaboration/generated | create_assembly* / solve_assembly. assembly.py + assembly_ops.py; solve_assembly is native-compat legacy. | `create_assembly`, `create_assembly_grounded_joint`, `create_assembly_joint`, `solve_assembly` |
| G-body-create-PASS | 1 | sequential if touching shared CI/collaboration/generated | Qualified reference slice. Do not regress. Files: addon body_create.py, body_mutation.py, collaboration_api.commit_body_create_mutation, body_create_contract.py (vendored pair), body_ops.py, ci/qualify_body_create.py, ci/check_body_create_contract.py, tests/test_body_create*.py, pyproject mypy files list, parent Woodpecker lint. | `body_create` |
| G-core-objects | 6 | sequential if touching shared CI/collaboration/generated | create/edit/delete/inspect/repair/insert + create_document. object_ops.py, object_crud.py, reference_ops.py, cad_mutation. Generated Any on create/edit/repair. | `create_document`, `create_object`, `delete_object`, `edit_object`, `inspect_references`, `repair_references` |
| G-document-gui | 26 | sequential if touching shared CI/collaboration/generated | document open/reload/close/recompute/undo/redo + remaining GUI not in N/A-gui set. interactive.py, document_ops.py, history_ops.py. | `activate_document`, `animate_placement`, `close_document`, `encode_view_video`, `get_gui_state`, `get_object`, `get_objects`, `get_parts_list`, `get_recompute_log`, `get_report_view`, `get_selection`, `get_view`… |
| G-escape | 3 | sequential if touching shared CI/collaboration/generated | execute_code, execute_code_async, run_transaction. Intentionally not typed CAD mutations. Do not assign a body_create-style worktree first. | `execute_code`, `execute_code_async`, `run_transaction` |
| G-features-p3 | 12 | sequential if touching shared CI/collaboration/generated | revolve/loft/sweep/helix/fillet/chamfer/boolean/pattern. Shared p3_features.py + feature_ops.py + execute-code templates. No addon native-compat except pad/pocket. | `boolean_difference`, `boolean_intersection`, `boolean_union`, `chamfer_feature`, `fillet_feature`, `helical_sweep_feature`, `linear_pattern_feature`, `loft_feature`, `mirror_feature`, `polar_pattern_feature`, `revolve_feature`, `sweep_feature` |
| G-gears | 5 | sequential if touching shared CI/collaboration/generated | p4_gears.py + feature_ops create_spur_gear. Execute-code. | `check_gear_pair`, `compute_gear_geometry`, `create_helical_gear`, `create_involute_gear`, `create_spur_gear` |
| G-io | 7 | sequential if touching shared CI/collaboration/generated | import/export. p6_io.py execute-code. Partial-rollback methods on export. | `export_brep`, `export_step`, `export_stl`, `get_document_tree`, `import_brep`, `import_step`, `set_color` |
| G-lease | 9 | sequential if touching shared CI/collaboration/generated | Lease tools. save/finalize are live typed connection methods. acquire/adopt/get/list/update/release generated MCP tools currently always return LEGACY_LEASE_AUTHORITY_REMOVED. Not a CAD typed-RPC worktree. | `acquire_document_lock`, `adopt_dirty_document`, `finalize_document_edit`, `get_document_lock`, `list_document_locks`, `release_document_lock`, `save_document`, `save_document_as`, `update_document_lock` |
| G-measure-transform | 12 | sequential if touching shared CI/collaboration/generated | measure_* mostly worker execute-code (some manifests wrongly mark MUTATION). translate/rotate/scale execute-code. | `bounding_box`, `center_of_mass`, `common_volume_along_path`, `get_global_shape`, `measure_angle`, `measure_area`, `measure_distance`, `measure_volume`, `rotate`, `scale`, `translate`, `validate_geometry` |
| G-parametric-sheet | 8 | sequential if touching shared CI/collaboration/generated | spreadsheet_* and set/clear/list_expression. Shared spreadsheet.py, expression_ops.py, spreadsheet_ops.py, cad_mutation for several. | `clear_expression`, `list_expressions`, `set_expression`, `spreadsheet_create`, `spreadsheet_get_cells`, `spreadsheet_list_aliases`, `spreadsheet_set_alias`, `spreadsheet_set_cells` |
| G-partdesign-assembly-helpers | 16 | sequential if touching shared CI/collaboration/generated | datum/binder/container/move/path/sweep_pipe/placement_*. Shared p7_assembly_ops/document_tree_ops.py and diagnostics mutation_ops.py. Execute-code. | `build_path_wire`, `create_datum_plane`, `create_part_container`, `create_placement_binder`, `create_placement_datum`, `create_subshape_binder`, `edge_axis`, `face_normal`, `find_edges`, `find_faces`, `get_sketch_geometry`, `move_object`… |
| G-partdesign-core | 10 | sequential if touching shared CI/collaboration/generated | Highest-priority CAD mutations after the reference. Shared: sketch_public.py, features_gui.py, sketch_gui_create.py, cad_mutation.py, collaboration_api.py, generated tools_parametric_body / tools_sketch_create_* / tools_features_basic_1. Sequential vs each other and vs body_create CI/mypy. | `body_set_tip`, `pad_feature`, `pocket_feature`, `sketch_add_constraint`, `sketch_add_geometry`, `sketch_attach`, `sketch_create`, `sketch_delete_constraint`, `sketch_delete_geometry`, `sketch_edit_constraint` |
| G-runtime | 7 | sequential if touching shared CI/collaboration/generated | get_runtime_info, check_rpc_sync, request status/claim/cancel, worker status/cancel. Not CAD mutations. | `cancel_request`, `cancel_worker_job`, `check_rpc_sync`, `claim_acquisition_result`, `get_request_status`, `get_runtime_info`, `get_worker_status` |
| G-sketch-execute-code | 29 | sequential if touching shared CI/collaboration/generated | Sketch primitive/curve/constraint/edit tools. Mostly execute-code templates under operations/core_ops/sketch_constraint_ops.py, p1_curves_ops, p2_editing.py, p1 templates. Parallelizable with PartDesign only if they do not touch sketch_public.py / cad_mutation.py / pyproject.toml / Woodpecker. | `sketch_add_arc`, `sketch_add_arc_of_ellipse`, `sketch_add_bezier`, `sketch_add_bspline`, `sketch_add_bspline_through_points`, `sketch_add_circle`, `sketch_add_ellipse`, `sketch_add_line`, `sketch_add_parametric_curve`, `sketch_add_polyline`, `sketch_add_rectangle`, `sketch_add_regular_polygon`… |

## Recommended Composer 2.5 worktrees

Creating first worktree now (`body_set_tip`).

### First isolated worktree (single operation)

| Field | Value |
| --- | --- |
| Operation | `body_set_tip` |
| Why isolated | Reference already split the legacy Tip path; unique client module + unique template + unique GUI apply helper; 3-string public API; can add **new** contract/mutation/qualify files without rewriting `body_create.py` / `body_create_contract.py` / `body_mutation.py` |
| Suggested parent worktree | `D:/code/FreeCAD-wt-body-set-tip` |
| Suggested parent branch | `feature/typed-rpc-body-set-tip` (from `feature/typed-rpc` @d0d82b743886) |
| Suggested MCP branch | `feature/typed-rpc-body-set-tip` (from `b32a13422a9d`) |
| Sequential overlaps | `collaboration_api.py` (add Tip-specific or generic native commit), `sketch_public.py` (one dispatcher), `features_gui.py` (remove leaf recompute from apply), `body_ops.py` re-export, `tools_parametric_body` regen, `pyproject.toml`, Woodpecker if a new `check_*` is wired |
| Do not edit | `body_create.py`, `body_create_contract.py`, `body_mutation.py` internals (copy the pattern into new files) |
| Do not hand-edit | `src/freecad_mcp/generated/**` |

### Next 2–3 sequential candidates (after `body_set_tip` merges or if sharing sketch_public/collaboration)

1. **`sketch_create`** — next in the documented Body → Sketch → Pad recipe; MCP is execute-code; addon RPC already exists; overlaps `sketch_ops.py`, `sketch_gui_create.py`, `sketch_public.py`.
2. **`sketch_attach`** — hybrid typed RPC + execute-code fallback; generated `Any`; lives in the same `tools_parametric_body` module as Body/Tip.
3. **`pad_feature`** — execute-code MCP; addon RPC + `_run_structural_feature`; overlaps `feature_ops.py`, `features_gui.py`, `sketch_public.py`.

Do **not** start these in parallel with `body_set_tip` if they will edit `collaboration_api.py`, `sketch_public.py`, `pyproject.toml`, or Woodpecker.

`sketch_delete_constraint` / `sketch_delete_geometry` already use a typed RPC **client**, but still FAIL native policy. They are **not** a smaller first worktree: they share `cad_mutation.py` / `sketch_public.py` and would tempt an adapter rewrite.

## Blockers

- None that block creating the `body_set_tip` worktree.
- Persistent constraints (not PASS claims):
  - Native `--native` lane needs branch-built FreeCAD (`freecad-ci-mcp:24.04-phase1` in the reference). Missing runtime is an error, not a skip.
  - Generated registrations must be regenerated.
  - `collaboration_api.py`, `pyproject.toml`, and Woodpecker lint are global serialization points.
  - Lease acquire/update/release MCP tools currently **always fail** with `LEGACY_LEASE_AUTHORITY_REMOVED` in generated registrations. Out of CAD typed-RPC scope; do not report as PASS.
  - This review did not execute tests or talk to a live FreeCAD.

## Honest limitations of this inventory

- Static code + manifest/generated parse only. **No** `uv run python ci/qualify_body_create.py`, **no** native FreeCAD, **no** MCP memory-session re-run.
- `body_create` PASS is copied from the reference document at older SHAs; current HEADs include a harden follow-up that was not re-executed here.
- Some operation wrappers were classified via AST (`_run_code` / `_run_json_code` / typed `freecad.<method>`). Boolean/measure/constraint helpers that call `_run_code` indirectly are still execute-code even if a row says “operation wrapper”.
- Live Cursor tool list can drift from this checkout (it already did for two stale names).
- Reads/gui/lease were not scored as FAIL; they also lack Body-style contracts. That is intentional: they are N/A for the CAD mutation matrix, not proven correct.

## Complete operation registry (171)

| Operation | Kind | Native txn | Impl path | Follows body_create | Status | Overlap group | Suggested branch | Evidence / limits |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `acquire_document_lock` | lease-control | no | lease-stub-removed | n/a | N/A-lease | G-lease | — | Lease lifecycle, not CAD mutation. Acquire/update/release generated tools currently stub to LEGACY_LEASE_AUTHORITY_REMOVED; save/finalize remain live connection methods. |
| `activate_document` | mutation | yes | typed-RPC client (no body_create contract) | no | FAIL | G-document-gui | feature/typed-rpc-activate-document | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `adopt_dirty_document` | lease-control | no | lease-stub-removed | n/a | N/A-lease | G-lease | — | Lease lifecycle, not CAD mutation. Acquire/update/release generated tools currently stub to LEGACY_LEASE_AUTHORITY_REMOVED; save/finalize remain live connection methods. |
| `animate_placement` | gui | no | typed-RPC client (no body_create contract) | n/a | N/A-gui | G-document-gui | — | View/selection/color tool. Outside CAD native-postcondition matrix. Not proven against body_create tests. |
| `audit_hardcoded_dimensions` | read | no | execute-code template | n/a | N/A-readonly | G-advanced-diagnostics | — | Read tool: native CAD transaction matrix does not apply. Many still use execute-code; not proven typed. |
| `body_create` | mutation | yes | typed-rpc-native (body_ops → JSON-RPC body_create) | yes | PASS | G-body-create-PASS | feature/typed-rpc (qualified) | Reference doc 2026-09-13: focused 218, native 16, collab/binding 77, ruff+arch/type, Woodpecker lint. Not re-run this inventory. |
| `body_set_tip` | mutation | yes | typed JSON-RPC (worktree, uncommitted) | partial | FAIL | G-partdesign-core | feature/typed-rpc-body-set-tip | Grok 2026-09-13: NOT PASS. Focused 161 + Body 218 + Docker lint OK. Native `--native` FAIL 1/1 (`Busy` from invalid empty-Pad fixture). Inspect protocol allows Tip writes. |
| `boolean_difference` | mutation | yes | operation wrapper (likely execute-code helper) | no | FAIL | G-features-p3 | feature/typed-rpc-boolean-difference | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `boolean_intersection` | mutation | yes | operation wrapper (likely execute-code helper) | no | FAIL | G-features-p3 | feature/typed-rpc-boolean-intersection | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `boolean_union` | mutation | yes | operation wrapper (likely execute-code helper) | no | FAIL | G-features-p3 | feature/typed-rpc-boolean-union | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `bounding_box` | mutation | yes | execute-code template | no | FAIL | G-measure-transform | feature/typed-rpc-bounding-box | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `build_path_wire` | mutation | yes | execute-code template | no | FAIL | G-partdesign-assembly-helpers | feature/typed-rpc-build-path-wire | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `cancel_request` | other | no | typed connection / inline register | n/a | N/A-runtime | G-runtime | — | Request/worker control, not a CAD modelling mutation. |
| `cancel_worker_job` | other | no | typed connection / inline register | n/a | N/A-runtime | G-runtime | — | Request/worker control, not a CAD modelling mutation. |
| `capture_state` | mutation | yes | execute-code template | no | FAIL | G-advanced-diagnostics | feature/typed-rpc-capture-state | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `center_of_mass` | mutation | yes | execute-code template | no | FAIL | G-measure-transform | feature/typed-rpc-center-of-mass | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `chamfer_feature` | mutation | yes | execute-code template | no | FAIL | G-features-p3 | feature/typed-rpc-chamfer-feature | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `check_gear_pair` | read | no | operation wrapper (likely execute-code helper) | n/a | N/A-readonly | G-gears | — | Read tool: native CAD transaction matrix does not apply. Many still use execute-code; not proven typed. |
| `check_rpc_sync` | read | no | typed connection / inline register | n/a | N/A-readonly | G-runtime | — | Read tool: native CAD transaction matrix does not apply. Many still use execute-code; not proven typed. |
| `claim_acquisition_result` | other | no | typed connection / inline register | n/a | N/A-runtime | G-runtime | — | Request/worker control, not a CAD modelling mutation. |
| `clear_expression` | mutation | yes | execute-code template | no | FAIL | G-parametric-sheet | feature/typed-rpc-clear-expression | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `close_document` | mutation | yes | typed-RPC client (no body_create contract) | no | FAIL | G-document-gui | feature/typed-rpc-close-document | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `common_volume_along_path` | mutation | yes | execute-code template | no | FAIL | G-measure-transform | feature/typed-rpc-common-volume-along-path | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `compare_documents` | read | no | execute-code template | n/a | N/A-readonly | G-advanced-diagnostics | — | Read tool: native CAD transaction matrix does not apply. Many still use execute-code; not proven typed. |
| `compute_gear_geometry` | read | no | operation wrapper (likely execute-code helper) | n/a | N/A-readonly | G-gears | — | Read tool: native CAD transaction matrix does not apply. Many still use execute-code; not proven typed. |
| `create_assembly` | mutation | yes | execute-code template | no | FAIL | G-assembly | feature/typed-rpc-create-assembly | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `create_assembly_grounded_joint` | mutation | yes | execute-code template | no | FAIL | G-assembly | feature/typed-rpc-create-assembly-grounded-joint | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `create_assembly_joint` | mutation | yes | execute-code template | no | FAIL | G-assembly | feature/typed-rpc-create-assembly-joint | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `create_datum_plane` | mutation | yes | execute-code template | no | FAIL | G-partdesign-assembly-helpers | feature/typed-rpc-create-datum-plane | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `create_document` | mutation | yes | typed-RPC client (no body_create contract) | no | FAIL | G-core-objects | feature/typed-rpc-create-document | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `create_helical_gear` | mutation | yes | execute-code template | no | FAIL | G-gears | feature/typed-rpc-create-helical-gear | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `create_involute_gear` | mutation | yes | execute-code template | no | FAIL | G-gears | feature/typed-rpc-create-involute-gear | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `create_object` | mutation | yes | typed-RPC client (no body_create contract) | no | FAIL | G-core-objects | feature/typed-rpc-create-object | Typed RPC client + addon run_cad_mutation legacy. Generated tool schema uses Any. No body_create-style contract or native-recompute postcondition. |
| `create_part_container` | mutation | yes | execute-code template | no | FAIL | G-partdesign-assembly-helpers | feature/typed-rpc-create-part-container | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `create_placement_binder` | mutation | yes | execute-code template | no | FAIL | G-partdesign-assembly-helpers | feature/typed-rpc-create-placement-binder | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `create_placement_datum` | mutation | yes | execute-code template | no | FAIL | G-partdesign-assembly-helpers | feature/typed-rpc-create-placement-datum | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `create_spur_gear` | mutation | yes | execute-code template | no | FAIL | G-gears | feature/typed-rpc-create-spur-gear | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `create_subshape_binder` | mutation | yes | execute-code template | no | FAIL | G-partdesign-assembly-helpers | feature/typed-rpc-create-subshape-binder | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `delete_object` | mutation | yes | execute-code template | no | FAIL | G-core-objects | feature/typed-rpc-delete-object | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `diagnose_helix` | read | no | execute-code template | n/a | N/A-readonly | G-advanced-diagnostics | — | Read tool: native CAD transaction matrix does not apply. Many still use execute-code; not proven typed. |
| `diagnose_parametric` | read | no | execute-code template | n/a | N/A-readonly | G-advanced-diagnostics | — | Read tool: native CAD transaction matrix does not apply. Many still use execute-code; not proven typed. |
| `diagnose_pocket` | read | no | execute-code template | n/a | N/A-readonly | G-advanced-diagnostics | — | Read tool: native CAD transaction matrix does not apply. Many still use execute-code; not proven typed. |
| `edge_axis` | read | no | operation wrapper (likely execute-code helper) | n/a | N/A-readonly | G-partdesign-assembly-helpers | — | Read tool: native CAD transaction matrix does not apply. Many still use execute-code; not proven typed. |
| `edit_object` | mutation | yes | typed-RPC client (no body_create contract) | no | FAIL | G-core-objects | feature/typed-rpc-edit-object | Typed RPC client + addon run_cad_mutation legacy. Generated tool schema uses Any. No body_create-style contract or native-recompute postcondition. |
| `encode_view_video` | gui | no | operation wrapper (likely execute-code helper) | n/a | N/A-gui | G-document-gui | — | View/selection/color tool. Outside CAD native-postcondition matrix. Not proven against body_create tests. |
| `execute_code` | execute-escape | no | execute-code template | n/a | N/A-escape | G-escape | — | execute_code / execute_code_async / run_transaction. Intentionally not a typed CAD mutation. |
| `execute_code_async` | execute-escape | no | operation wrapper (likely execute-code helper) | n/a | N/A-escape | G-escape | — | execute_code / execute_code_async / run_transaction. Intentionally not a typed CAD mutation. |
| `export_brep` | mutation | yes | execute-code template | no | FAIL | G-io | feature/typed-rpc-export-brep | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `export_step` | mutation | yes | execute-code template | no | FAIL | G-io | feature/typed-rpc-export-step | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `export_stl` | mutation | yes | execute-code template | no | FAIL | G-io | feature/typed-rpc-export-stl | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `face_normal` | read | no | operation wrapper (likely execute-code helper) | n/a | N/A-readonly | G-partdesign-assembly-helpers | — | Read tool: native CAD transaction matrix does not apply. Many still use execute-code; not proven typed. |
| `fillet_feature` | mutation | yes | execute-code template | no | FAIL | G-features-p3 | feature/typed-rpc-fillet-feature | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `finalize_document_edit` | lease-control | no | typed JSON-RPC connection method | n/a | N/A-lease | G-lease | — | Lease lifecycle, not CAD mutation. Acquire/update/release generated tools currently stub to LEGACY_LEASE_AUTHORITY_REMOVED; save/finalize remain live connection methods. |
| `find_edges` | read | no | operation wrapper (likely execute-code helper) | n/a | N/A-readonly | G-partdesign-assembly-helpers | — | Read tool: native CAD transaction matrix does not apply. Many still use execute-code; not proven typed. |
| `find_faces` | read | no | operation wrapper (likely execute-code helper) | n/a | N/A-readonly | G-partdesign-assembly-helpers | — | Read tool: native CAD transaction matrix does not apply. Many still use execute-code; not proven typed. |
| `geometric_diff` | read | no | execute-code template | n/a | N/A-readonly | G-advanced-diagnostics | — | Read tool: native CAD transaction matrix does not apply. Many still use execute-code; not proven typed. |
| `get_dependency_graph` | read | no | execute-code template | n/a | N/A-readonly | G-advanced-diagnostics | — | Read tool: native CAD transaction matrix does not apply. Many still use execute-code; not proven typed. |
| `get_document_lock` | lease-control | no | lease-stub-removed | n/a | N/A-lease | G-lease | — | Lease lifecycle, not CAD mutation. Acquire/update/release generated tools currently stub to LEGACY_LEASE_AUTHORITY_REMOVED; save/finalize remain live connection methods. |
| `get_document_tree` | read | no | execute-code template | n/a | N/A-readonly | G-io | — | Read tool: native CAD transaction matrix does not apply. Many still use execute-code; not proven typed. |
| `get_global_shape` | read | no | execute-code template | n/a | N/A-readonly | G-measure-transform | — | Read tool: native CAD transaction matrix does not apply. Many still use execute-code; not proven typed. |
| `get_gui_state` | gui | no | typed-RPC client (no body_create contract) | n/a | N/A-gui | G-document-gui | — | View/selection/color tool. Outside CAD native-postcondition matrix. Not proven against body_create tests. |
| `get_object` | read | no | typed-RPC client (no body_create contract) | n/a | N/A-readonly | G-document-gui | — | Read tool: native CAD transaction matrix does not apply. Many still use execute-code; not proven typed. |
| `get_objects` | read | no | typed-RPC client (no body_create contract) | n/a | N/A-readonly | G-document-gui | — | Read tool: native CAD transaction matrix does not apply. Many still use execute-code; not proven typed. |
| `get_parts_list` | read | no | typed-RPC client (no body_create contract) | n/a | N/A-readonly | G-document-gui | — | Read tool: native CAD transaction matrix does not apply. Many still use execute-code; not proven typed. |
| `get_recompute_log` | read | no | execute-code template | n/a | N/A-readonly | G-document-gui | — | Read tool: native CAD transaction matrix does not apply. Many still use execute-code; not proven typed. |
| `get_report_view` | gui | no | typed-RPC client (no body_create contract) | n/a | N/A-gui | G-document-gui | — | View/selection/color tool. Outside CAD native-postcondition matrix. Not proven against body_create tests. |
| `get_request_status` | read | no | typed connection / inline register | n/a | N/A-readonly | G-runtime | — | Read tool: native CAD transaction matrix does not apply. Many still use execute-code; not proven typed. |
| `get_runtime_info` | read | no | typed connection / inline register | n/a | N/A-readonly | G-runtime | — | Read tool: native CAD transaction matrix does not apply. Many still use execute-code; not proven typed. |
| `get_selection` | gui | no | typed-RPC client (no body_create contract) | n/a | N/A-gui | G-document-gui | — | View/selection/color tool. Outside CAD native-postcondition matrix. Not proven against body_create tests. |
| `get_sketch_diagnostics` | read | no | execute-code template | n/a | N/A-readonly | G-advanced-diagnostics | — | Read tool: native CAD transaction matrix does not apply. Many still use execute-code; not proven typed. |
| `get_sketch_geometry` | read | no | execute-code template | n/a | N/A-readonly | G-partdesign-assembly-helpers | — | Read tool: native CAD transaction matrix does not apply. Many still use execute-code; not proven typed. |
| `get_view` | gui | no | operation wrapper (likely execute-code helper) | n/a | N/A-gui | G-document-gui | — | View/selection/color tool. Outside CAD native-postcondition matrix. Not proven against body_create tests. |
| `get_worker_status` | read | no | typed connection / inline register | n/a | N/A-readonly | G-runtime | — | Read tool: native CAD transaction matrix does not apply. Many still use execute-code; not proven typed. |
| `helical_sweep_feature` | mutation | yes | execute-code template | no | FAIL | G-features-p3 | feature/typed-rpc-helical-sweep-feature | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `import_brep` | mutation | yes | execute-code template | no | FAIL | G-io | feature/typed-rpc-import-brep | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `import_step` | mutation | yes | execute-code template | no | FAIL | G-io | feature/typed-rpc-import-step | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `insert_part_from_library` | mutation | yes | typed-RPC client (no body_create contract) | no | FAIL | G-document-gui | feature/typed-rpc-insert-part-from-library | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `inspect_geometry` | read | no | hybrid typed-RPC then execute-code fallback | n/a | N/A-readonly | G-advanced-diagnostics | — | Read tool: native CAD transaction matrix does not apply. Many still use execute-code; not proven typed. |
| `inspect_references` | read | no | typed-RPC client (no body_create contract) | n/a | N/A-readonly | G-core-objects | — | Read tool: native CAD transaction matrix does not apply. Many still use execute-code; not proven typed. |
| `linear_pattern_feature` | mutation | yes | execute-code template | no | FAIL | G-features-p3 | feature/typed-rpc-linear-pattern-feature | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `list_document_locks` | lease-control | no | lease-stub-removed | n/a | N/A-lease | G-lease | — | Lease lifecycle, not CAD mutation. Acquire/update/release generated tools currently stub to LEGACY_LEASE_AUTHORITY_REMOVED; save/finalize remain live connection methods. |
| `list_documents` | read | no | typed-RPC client (no body_create contract) | n/a | N/A-readonly | G-document-gui | — | Read tool: native CAD transaction matrix does not apply. Many still use execute-code; not proven typed. |
| `list_expressions` | read | no | execute-code template | n/a | N/A-readonly | G-parametric-sheet | — | Read tool: native CAD transaction matrix does not apply. Many still use execute-code; not proven typed. |
| `loft_feature` | mutation | yes | execute-code template | no | FAIL | G-features-p3 | feature/typed-rpc-loft-feature | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `match_subshape` | read | no | execute-code template | n/a | N/A-readonly | G-advanced-diagnostics | — | Read tool: native CAD transaction matrix does not apply. Many still use execute-code; not proven typed. |
| `measure_angle` | read | no | execute-code template | n/a | N/A-readonly | G-measure-transform | — | Read tool: native CAD transaction matrix does not apply. Many still use execute-code; not proven typed. |
| `measure_area` | read | no | execute-code template | n/a | N/A-readonly | G-measure-transform | — | Read tool: native CAD transaction matrix does not apply. Many still use execute-code; not proven typed. |
| `measure_distance` | read | no | execute-code template | n/a | N/A-readonly | G-measure-transform | — | Read tool: native CAD transaction matrix does not apply. Many still use execute-code; not proven typed. |
| `measure_volume` | read | no | execute-code template | n/a | N/A-readonly | G-measure-transform | — | Read tool: native CAD transaction matrix does not apply. Many still use execute-code; not proven typed. |
| `mirror_feature` | mutation | yes | execute-code template | no | FAIL | G-features-p3 | feature/typed-rpc-mirror-feature | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `move_object` | mutation | yes | execute-code template | no | FAIL | G-partdesign-assembly-helpers | feature/typed-rpc-move-object | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `open_document` | mutation | yes | typed-RPC client (no body_create contract) | no | FAIL | G-document-gui | feature/typed-rpc-open-document | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `pad_feature` | mutation | yes | execute-code template | no | FAIL | G-partdesign-core | feature/typed-rpc-pad-feature | MCP tool still renders execute-code templates even though addon JSON-RPC + run_cad_mutation exist. Legacy adapter does not opt into native_recompute. |
| `placement_audit` | read | no | execute-code template | n/a | N/A-readonly | G-partdesign-assembly-helpers | — | Read tool: native CAD transaction matrix does not apply. Many still use execute-code; not proven typed. |
| `pocket_feature` | mutation | yes | execute-code template | no | FAIL | G-partdesign-core | feature/typed-rpc-pocket-feature | MCP tool still renders execute-code templates even though addon JSON-RPC + run_cad_mutation exist. Legacy adapter does not opt into native_recompute. |
| `polar_pattern_feature` | mutation | yes | execute-code template | no | FAIL | G-features-p3 | feature/typed-rpc-polar-pattern-feature | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `preview_attachment` | mutation | yes | execute-code template | no | FAIL | G-partdesign-assembly-helpers | feature/typed-rpc-preview-attachment | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `recompute_and_wait` | mutation | yes | typed-RPC client (no body_create contract) | no | FAIL | G-document-gui | feature/typed-rpc-recompute-and-wait | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `recompute_document` | mutation | yes | execute-code template | no | FAIL | G-document-gui | feature/typed-rpc-recompute-document | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `redo` | mutation | yes | execute-code template | no | FAIL | G-document-gui | feature/typed-rpc-redo | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `refresh_view` | gui | no | typed-RPC client (no body_create contract) | n/a | N/A-gui | G-document-gui | — | View/selection/color tool. Outside CAD native-postcondition matrix. Not proven against body_create tests. |
| `release_document_lock` | lease-control | no | lease-stub-removed | n/a | N/A-lease | G-lease | — | Lease lifecycle, not CAD mutation. Acquire/update/release generated tools currently stub to LEGACY_LEASE_AUTHORITY_REMOVED; save/finalize remain live connection methods. |
| `relink_references` | mutation | yes | execute-code template | no | FAIL | G-advanced-diagnostics | feature/typed-rpc-relink-references | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `reload_document` | mutation | yes | typed-RPC client (no body_create contract) | no | FAIL | G-document-gui | feature/typed-rpc-reload-document | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `repair_references` | mutation | yes | typed-RPC client (no body_create contract) | no | FAIL | G-core-objects | feature/typed-rpc-repair-references | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `repair_view_placements` | gui | no | typed-RPC client (no body_create contract) | n/a | N/A-gui | G-document-gui | — | View/selection/color tool. Outside CAD native-postcondition matrix. Not proven against body_create tests. |
| `restore` | mutation | yes | typed-RPC client (no body_create contract) | no | FAIL | G-advanced-diagnostics | feature/typed-rpc-restore | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `revolve_feature` | mutation | yes | execute-code template | no | FAIL | G-features-p3 | feature/typed-rpc-revolve-feature | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `rotate` | mutation | yes | execute-code template | no | FAIL | G-measure-transform | feature/typed-rpc-rotate | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `run_fem_analysis` | mutation | yes | typed-RPC client (no body_create contract) | no | FAIL | G-advanced-diagnostics | feature/typed-rpc-run-fem-analysis | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `run_transaction` | execute-escape | no | execute-code template | n/a | N/A-escape | G-escape | — | execute_code / execute_code_async / run_transaction. Intentionally not a typed CAD mutation. |
| `save_document` | lease-control | no | typed JSON-RPC connection method | n/a | N/A-lease | G-lease | — | Lease lifecycle, not CAD mutation. Acquire/update/release generated tools currently stub to LEGACY_LEASE_AUTHORITY_REMOVED; save/finalize remain live connection methods. |
| `save_document_as` | lease-control | no | typed JSON-RPC connection method | n/a | N/A-lease | G-lease | — | Lease lifecycle, not CAD mutation. Acquire/update/release generated tools currently stub to LEGACY_LEASE_AUTHORITY_REMOVED; save/finalize remain live connection methods. |
| `save_view_sequence` | gui | no | operation wrapper (likely execute-code helper) | n/a | N/A-gui | G-document-gui | — | View/selection/color tool. Outside CAD native-postcondition matrix. Not proven against body_create tests. |
| `scale` | mutation | yes | execute-code template | no | FAIL | G-measure-transform | feature/typed-rpc-scale | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `select_subshapes` | gui | no | typed-RPC client (no body_create contract) | n/a | N/A-gui | G-document-gui | — | View/selection/color tool. Outside CAD native-postcondition matrix. Not proven against body_create tests. |
| `set_color` | gui | no | execute-code template | n/a | N/A-gui | G-io | — | View/selection/color tool. Outside CAD native-postcondition matrix. Not proven against body_create tests. |
| `set_expression` | mutation | yes | execute-code template | no | FAIL | G-parametric-sheet | feature/typed-rpc-set-expression | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `set_section_view` | gui | no | typed-RPC client (no body_create contract) | n/a | N/A-gui | G-document-gui | — | View/selection/color tool. Outside CAD native-postcondition matrix. Not proven against body_create tests. |
| `set_tree_expanded` | gui | no | typed-RPC client (no body_create contract) | n/a | N/A-gui | G-document-gui | — | View/selection/color tool. Outside CAD native-postcondition matrix. Not proven against body_create tests. |
| `sketch_add_arc` | mutation | yes | execute-code template | no | FAIL | G-sketch-execute-code | feature/typed-rpc-sketch-add-arc | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `sketch_add_arc_of_ellipse` | mutation | yes | execute-code template | no | FAIL | G-sketch-execute-code | feature/typed-rpc-sketch-add-arc-of-ellipse | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `sketch_add_bezier` | mutation | yes | execute-code template | no | FAIL | G-sketch-execute-code | feature/typed-rpc-sketch-add-bezier | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `sketch_add_bspline` | mutation | yes | execute-code template | no | FAIL | G-sketch-execute-code | feature/typed-rpc-sketch-add-bspline | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `sketch_add_bspline_through_points` | mutation | yes | execute-code template | no | FAIL | G-sketch-execute-code | feature/typed-rpc-sketch-add-bspline-through-points | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `sketch_add_circle` | mutation | yes | execute-code template | no | FAIL | G-sketch-execute-code | feature/typed-rpc-sketch-add-circle | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `sketch_add_constraint` | mutation | yes | execute-code template | no | FAIL | G-partdesign-core | feature/typed-rpc-sketch-add-constraint | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `sketch_add_ellipse` | mutation | yes | execute-code template | no | FAIL | G-sketch-execute-code | feature/typed-rpc-sketch-add-ellipse | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `sketch_add_external_projection` | mutation | yes | execute-code template | no | FAIL | G-partdesign-assembly-helpers | feature/typed-rpc-sketch-add-external-projection | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `sketch_add_geometry` | mutation | yes | execute-code template | no | FAIL | G-partdesign-core | feature/typed-rpc-sketch-add-geometry | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `sketch_add_line` | mutation | yes | execute-code template | no | FAIL | G-sketch-execute-code | feature/typed-rpc-sketch-add-line | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `sketch_add_parametric_curve` | mutation | yes | execute-code template | no | FAIL | G-sketch-execute-code | feature/typed-rpc-sketch-add-parametric-curve | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `sketch_add_polyline` | mutation | yes | execute-code template | no | FAIL | G-sketch-execute-code | feature/typed-rpc-sketch-add-polyline | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `sketch_add_rectangle` | mutation | yes | execute-code template | no | FAIL | G-sketch-execute-code | feature/typed-rpc-sketch-add-rectangle | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `sketch_add_regular_polygon` | mutation | yes | execute-code template | no | FAIL | G-sketch-execute-code | feature/typed-rpc-sketch-add-regular-polygon | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `sketch_add_slot` | mutation | yes | execute-code template | no | FAIL | G-sketch-execute-code | feature/typed-rpc-sketch-add-slot | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `sketch_attach` | mutation | yes | hybrid typed-RPC then execute-code fallback | no | FAIL | G-partdesign-core | feature/typed-rpc-sketch-attach | Tries freecad.sketch_attach then execute-code fallback. Generated schema uses Any. Addon uses legacy cad_mutation. Fallback after a started mutation is a known hazard. |
| `sketch_constrain_coincident` | mutation | yes | operation wrapper (likely execute-code helper) | no | FAIL | G-sketch-execute-code | feature/typed-rpc-sketch-constrain-coincident | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `sketch_constrain_distance` | mutation | yes | operation wrapper (likely execute-code helper) | no | FAIL | G-sketch-execute-code | feature/typed-rpc-sketch-constrain-distance | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `sketch_constrain_equal` | mutation | yes | operation wrapper (likely execute-code helper) | no | FAIL | G-sketch-execute-code | feature/typed-rpc-sketch-constrain-equal | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `sketch_constrain_horizontal` | mutation | yes | operation wrapper (likely execute-code helper) | no | FAIL | G-sketch-execute-code | feature/typed-rpc-sketch-constrain-horizontal | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `sketch_constrain_parallel` | mutation | yes | operation wrapper (likely execute-code helper) | no | FAIL | G-sketch-execute-code | feature/typed-rpc-sketch-constrain-parallel | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `sketch_constrain_perpendicular` | mutation | yes | operation wrapper (likely execute-code helper) | no | FAIL | G-sketch-execute-code | feature/typed-rpc-sketch-constrain-perpendicular | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `sketch_constrain_radius` | mutation | yes | operation wrapper (likely execute-code helper) | no | FAIL | G-sketch-execute-code | feature/typed-rpc-sketch-constrain-radius | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `sketch_constrain_tangent` | mutation | yes | operation wrapper (likely execute-code helper) | no | FAIL | G-sketch-execute-code | feature/typed-rpc-sketch-constrain-tangent | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `sketch_constrain_vertical` | mutation | yes | operation wrapper (likely execute-code helper) | no | FAIL | G-sketch-execute-code | feature/typed-rpc-sketch-constrain-vertical | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `sketch_create` | mutation | yes | execute-code template | no | FAIL | G-partdesign-core | feature/typed-rpc-sketch-create | MCP tool still renders execute-code templates even though addon JSON-RPC + run_cad_mutation exist. Legacy adapter does not opt into native_recompute. |
| `sketch_delete_constraint` | mutation | yes | typed-RPC client (no body_create contract) | no | FAIL | G-partdesign-core | feature/typed-rpc-sketch-delete-constraint | MCP client already calls typed RPC, but addon uses legacy cad_mutation (leaf-owned recompute, Any, historical envelope). No versioned contract/qualify lane. |
| `sketch_delete_geometry` | mutation | yes | typed-RPC client (no body_create contract) | no | FAIL | G-partdesign-core | feature/typed-rpc-sketch-delete-geometry | MCP client already calls typed RPC, but addon uses legacy cad_mutation (leaf-owned recompute, Any, historical envelope). No versioned contract/qualify lane. |
| `sketch_edit_constraint` | mutation | yes | execute-code template | no | FAIL | G-partdesign-core | feature/typed-rpc-sketch-edit-constraint | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `sketch_extend` | mutation | yes | execute-code template | no | FAIL | G-sketch-execute-code | feature/typed-rpc-sketch-extend | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `sketch_fillet` | mutation | yes | execute-code template | no | FAIL | G-sketch-execute-code | feature/typed-rpc-sketch-fillet | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `sketch_import_points` | mutation | yes | execute-code template | no | FAIL | G-sketch-execute-code | feature/typed-rpc-sketch-import-points | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `sketch_split` | mutation | yes | execute-code template | no | FAIL | G-sketch-execute-code | feature/typed-rpc-sketch-split | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `sketch_symmetry` | mutation | yes | execute-code template | no | FAIL | G-sketch-execute-code | feature/typed-rpc-sketch-symmetry | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `sketch_toggle_construction` | mutation | yes | execute-code template | no | FAIL | G-sketch-execute-code | feature/typed-rpc-sketch-toggle-construction | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `sketch_trim` | mutation | yes | execute-code template | no | FAIL | G-sketch-execute-code | feature/typed-rpc-sketch-trim | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `snapshot` | mutation | yes | typed-RPC client (no body_create contract) | no | FAIL | G-advanced-diagnostics | feature/typed-rpc-snapshot | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `solve_assembly` | mutation | yes | execute-code template | no | FAIL | G-assembly | feature/typed-rpc-solve-assembly | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `spreadsheet_create` | mutation | yes | execute-code template | no | FAIL | G-parametric-sheet | feature/typed-rpc-spreadsheet-create | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `spreadsheet_get_cells` | mutation | yes | execute-code template | no | FAIL | G-parametric-sheet | feature/typed-rpc-spreadsheet-get-cells | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `spreadsheet_list_aliases` | mutation | yes | execute-code template | no | FAIL | G-parametric-sheet | feature/typed-rpc-spreadsheet-list-aliases | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `spreadsheet_set_alias` | mutation | yes | execute-code template | no | FAIL | G-parametric-sheet | feature/typed-rpc-spreadsheet-set-alias | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `spreadsheet_set_cells` | mutation | yes | execute-code template | no | FAIL | G-parametric-sheet | feature/typed-rpc-spreadsheet-set-cells | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `sweep_feature` | mutation | yes | execute-code template | no | FAIL | G-features-p3 | feature/typed-rpc-sweep-feature | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `sweep_pipe` | mutation | yes | execute-code template | no | FAIL | G-partdesign-assembly-helpers | feature/typed-rpc-sweep-pipe | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `translate` | mutation | yes | execute-code template | no | FAIL | G-measure-transform | feature/typed-rpc-translate | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `undo` | mutation | yes | execute-code template | no | FAIL | G-document-gui | feature/typed-rpc-undo | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |
| `update_document_lock` | lease-control | no | lease-stub-removed | n/a | N/A-lease | G-lease | — | Lease lifecycle, not CAD mutation. Acquire/update/release generated tools currently stub to LEGACY_LEASE_AUTHORITY_REMOVED; save/finalize remain live connection methods. |
| `validate_geometry` | read | no | execute-code template | n/a | N/A-readonly | G-measure-transform | — | Read tool: native CAD transaction matrix does not apply. Many still use execute-code; not proven typed. |
| `validate_movement_follow` | mutation | yes | execute-code template | no | FAIL | G-advanced-diagnostics | feature/typed-rpc-validate-movement-follow | Does not match body_create acceptance table (see shared FAIL gaps). No qualify_<op>.py. |

## FAIL mutations (Composer CAD queue)

| Operation | Impl path | Overlap group | Verdict |
| --- | --- | --- | --- |
| `activate_document` | typed-RPC client (no body_create contract) | G-document-gui | FAIL |
| `body_set_tip` | typed JSON-RPC (worktree; Grok NOT PASS) | G-partdesign-core | FAIL |
| `boolean_difference` | operation wrapper (likely execute-code helper) | G-features-p3 | FAIL |
| `boolean_intersection` | operation wrapper (likely execute-code helper) | G-features-p3 | FAIL |
| `boolean_union` | operation wrapper (likely execute-code helper) | G-features-p3 | FAIL |
| `bounding_box` | execute-code template | G-measure-transform | FAIL |
| `build_path_wire` | execute-code template | G-partdesign-assembly-helpers | FAIL |
| `capture_state` | execute-code template | G-advanced-diagnostics | FAIL |
| `center_of_mass` | execute-code template | G-measure-transform | FAIL |
| `chamfer_feature` | execute-code template | G-features-p3 | FAIL |
| `clear_expression` | execute-code template | G-parametric-sheet | FAIL |
| `close_document` | typed-RPC client (no body_create contract) | G-document-gui | FAIL |
| `common_volume_along_path` | execute-code template | G-measure-transform | FAIL |
| `create_assembly` | execute-code template | G-assembly | FAIL |
| `create_assembly_grounded_joint` | execute-code template | G-assembly | FAIL |
| `create_assembly_joint` | execute-code template | G-assembly | FAIL |
| `create_datum_plane` | execute-code template | G-partdesign-assembly-helpers | FAIL |
| `create_document` | typed-RPC client (no body_create contract) | G-core-objects | FAIL |
| `create_helical_gear` | execute-code template | G-gears | FAIL |
| `create_involute_gear` | execute-code template | G-gears | FAIL |
| `create_object` | typed-RPC client (no body_create contract) | G-core-objects | FAIL |
| `create_part_container` | execute-code template | G-partdesign-assembly-helpers | FAIL |
| `create_placement_binder` | execute-code template | G-partdesign-assembly-helpers | FAIL |
| `create_placement_datum` | execute-code template | G-partdesign-assembly-helpers | FAIL |
| `create_spur_gear` | execute-code template | G-gears | FAIL |
| `create_subshape_binder` | execute-code template | G-partdesign-assembly-helpers | FAIL |
| `delete_object` | execute-code template | G-core-objects | FAIL |
| `edit_object` | typed-RPC client (no body_create contract) | G-core-objects | FAIL |
| `export_brep` | execute-code template | G-io | FAIL |
| `export_step` | execute-code template | G-io | FAIL |
| `export_stl` | execute-code template | G-io | FAIL |
| `fillet_feature` | execute-code template | G-features-p3 | FAIL |
| `helical_sweep_feature` | execute-code template | G-features-p3 | FAIL |
| `import_brep` | execute-code template | G-io | FAIL |
| `import_step` | execute-code template | G-io | FAIL |
| `insert_part_from_library` | typed-RPC client (no body_create contract) | G-document-gui | FAIL |
| `linear_pattern_feature` | execute-code template | G-features-p3 | FAIL |
| `loft_feature` | execute-code template | G-features-p3 | FAIL |
| `mirror_feature` | execute-code template | G-features-p3 | FAIL |
| `move_object` | execute-code template | G-partdesign-assembly-helpers | FAIL |
| `open_document` | typed-RPC client (no body_create contract) | G-document-gui | FAIL |
| `pad_feature` | execute-code template | G-partdesign-core | FAIL |
| `pocket_feature` | execute-code template | G-partdesign-core | FAIL |
| `polar_pattern_feature` | execute-code template | G-features-p3 | FAIL |
| `preview_attachment` | execute-code template | G-partdesign-assembly-helpers | FAIL |
| `recompute_and_wait` | typed-RPC client (no body_create contract) | G-document-gui | FAIL |
| `recompute_document` | execute-code template | G-document-gui | FAIL |
| `redo` | execute-code template | G-document-gui | FAIL |
| `relink_references` | execute-code template | G-advanced-diagnostics | FAIL |
| `reload_document` | typed-RPC client (no body_create contract) | G-document-gui | FAIL |
| `repair_references` | typed-RPC client (no body_create contract) | G-core-objects | FAIL |
| `restore` | typed-RPC client (no body_create contract) | G-advanced-diagnostics | FAIL |
| `revolve_feature` | execute-code template | G-features-p3 | FAIL |
| `rotate` | execute-code template | G-measure-transform | FAIL |
| `run_fem_analysis` | typed-RPC client (no body_create contract) | G-advanced-diagnostics | FAIL |
| `scale` | execute-code template | G-measure-transform | FAIL |
| `set_expression` | execute-code template | G-parametric-sheet | FAIL |
| `sketch_add_arc` | execute-code template | G-sketch-execute-code | FAIL |
| `sketch_add_arc_of_ellipse` | execute-code template | G-sketch-execute-code | FAIL |
| `sketch_add_bezier` | execute-code template | G-sketch-execute-code | FAIL |
| `sketch_add_bspline` | execute-code template | G-sketch-execute-code | FAIL |
| `sketch_add_bspline_through_points` | execute-code template | G-sketch-execute-code | FAIL |
| `sketch_add_circle` | execute-code template | G-sketch-execute-code | FAIL |
| `sketch_add_constraint` | execute-code template | G-partdesign-core | FAIL |
| `sketch_add_ellipse` | execute-code template | G-sketch-execute-code | FAIL |
| `sketch_add_external_projection` | execute-code template | G-partdesign-assembly-helpers | FAIL |
| `sketch_add_geometry` | execute-code template | G-partdesign-core | FAIL |
| `sketch_add_line` | execute-code template | G-sketch-execute-code | FAIL |
| `sketch_add_parametric_curve` | execute-code template | G-sketch-execute-code | FAIL |
| `sketch_add_polyline` | execute-code template | G-sketch-execute-code | FAIL |
| `sketch_add_rectangle` | execute-code template | G-sketch-execute-code | FAIL |
| `sketch_add_regular_polygon` | execute-code template | G-sketch-execute-code | FAIL |
| `sketch_add_slot` | execute-code template | G-sketch-execute-code | FAIL |
| `sketch_attach` | hybrid typed-RPC then execute-code fallback | G-partdesign-core | FAIL |
| `sketch_constrain_coincident` | operation wrapper (likely execute-code helper) | G-sketch-execute-code | FAIL |
| `sketch_constrain_distance` | operation wrapper (likely execute-code helper) | G-sketch-execute-code | FAIL |
| `sketch_constrain_equal` | operation wrapper (likely execute-code helper) | G-sketch-execute-code | FAIL |
| `sketch_constrain_horizontal` | operation wrapper (likely execute-code helper) | G-sketch-execute-code | FAIL |
| `sketch_constrain_parallel` | operation wrapper (likely execute-code helper) | G-sketch-execute-code | FAIL |
| `sketch_constrain_perpendicular` | operation wrapper (likely execute-code helper) | G-sketch-execute-code | FAIL |
| `sketch_constrain_radius` | operation wrapper (likely execute-code helper) | G-sketch-execute-code | FAIL |
| `sketch_constrain_tangent` | operation wrapper (likely execute-code helper) | G-sketch-execute-code | FAIL |
| `sketch_constrain_vertical` | operation wrapper (likely execute-code helper) | G-sketch-execute-code | FAIL |
| `sketch_create` | execute-code template | G-partdesign-core | FAIL |
| `sketch_delete_constraint` | typed-RPC client (no body_create contract) | G-partdesign-core | FAIL |
| `sketch_delete_geometry` | typed-RPC client (no body_create contract) | G-partdesign-core | FAIL |
| `sketch_edit_constraint` | execute-code template | G-partdesign-core | FAIL |
| `sketch_extend` | execute-code template | G-sketch-execute-code | FAIL |
| `sketch_fillet` | execute-code template | G-sketch-execute-code | FAIL |
| `sketch_import_points` | execute-code template | G-sketch-execute-code | FAIL |
| `sketch_split` | execute-code template | G-sketch-execute-code | FAIL |
| `sketch_symmetry` | execute-code template | G-sketch-execute-code | FAIL |
| `sketch_toggle_construction` | execute-code template | G-sketch-execute-code | FAIL |
| `sketch_trim` | execute-code template | G-sketch-execute-code | FAIL |
| `snapshot` | typed-RPC client (no body_create contract) | G-advanced-diagnostics | FAIL |
| `solve_assembly` | execute-code template | G-assembly | FAIL |
| `spreadsheet_create` | execute-code template | G-parametric-sheet | FAIL |
| `spreadsheet_get_cells` | execute-code template | G-parametric-sheet | FAIL |
| `spreadsheet_list_aliases` | execute-code template | G-parametric-sheet | FAIL |
| `spreadsheet_set_alias` | execute-code template | G-parametric-sheet | FAIL |
| `spreadsheet_set_cells` | execute-code template | G-parametric-sheet | FAIL |
| `sweep_feature` | execute-code template | G-features-p3 | FAIL |
| `sweep_pipe` | execute-code template | G-partdesign-assembly-helpers | FAIL |
| `translate` | execute-code template | G-measure-transform | FAIL |
| `undo` | execute-code template | G-document-gui | FAIL |
| `validate_movement_follow` | execute-code template | G-advanced-diagnostics | FAIL |

## Worktrees (roundup inventory)

| Worktree path | Branch | HEAD | Operations | Submodule checkout | Status |
| --- | --- | --- | --- | --- | --- |
| `D:/code/FreeCAD` | `feature/typed-rpc` | `07d75f0497` | tracker + platform LANDED | MCP `374a59b` on `feature/typed-rpc` | clean; PR #53 |
| `D:/code/FreeCAD-wt-body-set-tip` | `feature/typed-rpc-body-set-tip` | `07d75f0497` | `body_set_tip` | MCP `374a59b` on `feature/typed-rpc-body-set-tip` | **NOT PASS** — parent reset to platform SHA; Tip-only files restored **unstaged**; unpark incomplete |
| `D:/code/FreeCAD-wt-sketch-create` | `feature/typed-rpc-sketch-create` | `07d75f0497` | `sketch_create` | MCP `374a59b` on `feature/typed-rpc-sketch-create` | **NOT PASS** — setup only, no typed files |
| `D:/code/FreeCAD-wt-sketch-attach` | `feature/typed-rpc-sketch-attach` | `07d75f0497` | `sketch_attach` | MCP on `feature/typed-rpc-sketch-attach` @ `374a59b` | **NOT PASS** — setup only |
| `D:/code/FreeCAD-wt-pad-feature` | `feature/typed-rpc-pad-feature` | `07d75f0497` | `pad_feature` | MCP @ `374a59b` (detached; may not be isolated git worktree) | **NOT PASS** — setup only |

### `body_set_tip` worktree evidence (Composer claimed; **Grok independently re-ran**)

| Lane | Command | Composer | Grok independent |
| --- | --- | --- | --- |
| Tip qualify (focused) | `uv run python ci/qualify_body_set_tip.py` | 161 passed | **161 passed** |
| Body regression | `uv run python ci/qualify_body_create.py` | 218 passed | **218 passed** |
| Woodpecker lint | `docker run --rm -v D:/code/FreeCAD-wt-body-set-tip:/work -w /work python:3.12 sh ci/woodpecker/freecad-mcp-lint.sh` | OK | **OK** |
| Native `--native` | `python3 ci/qualify_body_set_tip.py --native` in `freecad-ci-mcp:24.04-phase1` + host `build_docker` libs | Composer claimed 14 passed | **Grok ×3: 13/14, 14/14, 13/14 (flaky).** Busy/empty-Pad fixture is gone. |

Implementation summary: typed JSON-RPC path via `body_set_tip.py` + `body_set_tip_mutation.py` + `body_set_tip_contract.py` (vendored pair); `commit_body_set_tip_mutation` in `collaboration_api.py`; MCP client `body_set_tip_operation` calls `freecad.body_set_tip()`; legacy execute-code kept in `body_set_tip_legacy.py` (outside typed slice).

Files touched (MCP worktree, uncommitted): new contract/apply/mutation/CI/tests/typecheck modules; modified `collaboration_api.py`, `cad_dependencies.py`, `collaboration_dependencies.py`, `sketch_public.py`, `features_gui.py` (removed leaf `recompute`), `body_set_tip.py` client, `freecad_connection.py`, `pyproject.toml`, `ci/check_body_create_contract.py`, `tests/test_body_create_contract_gate.py`, `tests/test_parametric.py`; parent worktree `ci/woodpecker/freecad-mcp-lint.sh` adds Tip gate.

## Commits / PRs / CI

| Date | Repo | SHA | PR | CI | Notes |
| --- | --- | --- | --- | --- | --- |
| 2026-09-13 | MCP (reference qualify) | `c4fa4f5562e2319606945efc7c1aa0767ad5f9d9` | — | reference lane PASS | From `body-create-reference.md` |
| 2026-09-13 | parent (reference qualify) | `b253505340ce45d0d6720bc9894f0e063e6196e5` | — | Woodpecker lint PASS in python:3.12 | From `body-create-reference.md` |
| 2026-09-13 | MCP HEAD (this inventory) | `b32a13422a9d18c65695806cf157f2cb1d153c6c` | — | not re-run | Harden body_create after reference base |
| 2026-09-13 | parent HEAD (this inventory) | `d0d82b74388674b22bf7e4aea89285f0ed71baff` | — | not re-run | Enforces typed Body contract in Woodpecker |
| 2026-09-13 | MCP (platform landing) | `374a59b7f8e74e6f15c6326db00abdd5fb0f3f38` | [PR #17](https://github.com/Rchiemstra/freecad-mcp/pull/17) | **no checks**; mergeable **CONFLICTING/DIRTY** | Typed RPC discovery + static globs + contract gates |
| 2026-09-13 | parent (platform landing) | `07d75f049719b48d72590d07452be6f67732bd4d` | [PR #53](https://github.com/Rchiemstra/FreeCAD/pull/53) | Labeler **SUCCESS** only; Prepare/Ubuntu/Lint + Woodpecker **not scheduled**; mergeable **CONFLICTING/DIRTY** | Submodule pin + Woodpecker `run_contract_checks.py` |
| 2026-09-13 | MCP (roundup docs) | pending | — | — | Canonical progress + handover in `doc/` |

## Review log

| When | Reviewer | Subject | Verdict | Notes |
| --- | --- | --- | --- | --- |
| 2026-09-13 | orchestrator | kickoff | n/a | Progress file created; full inventory delegated |
| 2026-09-13 | Grok `cursor-grok-4.6-xhigh` | 171 generated tools vs `body_create` | inventory complete | 1 PASS, 106 FAIL mutations, remainder N/A; first Composer op `body_set_tip` |
| 2026-09-13 | Grok `cursor-grok-4.6-xhigh` | `body_set_tip` typed-RPC vs body_create acceptance | **NOT PASS** | Areas 1–4,6,7,9,10 PASS; 5 FAIL (writable Tip on inspect); 8 FAIL (native test Busy, no matrix). Focused 161 / Body 218 / Docker lint OK. Do not commit. |
| 2026-09-13 | Grok `cursor-grok-4.6-xhigh` | `body_set_tip` re-review after protocol+native fixes | **NOT PASS** | Area 5 PASS. Area 8 FAIL: native flaky 13/14–14/14. Focused 161 / Body 218 / Docker lint OK. Same worktree; do not commit. |
| 2026-09-13 | Grok `cursor-grok-4.6-xhigh` | typed-rpc-platform on main | **NOT PASS** | Req 1,2,4,5,6 PASS. Req 3,7,8 FAIL (pyproject Any still Body-only; CadCollaborators/RPC bind still per-op; tests are glob strings). Body 222 / native 16 / Docker lint OK. Composer on main; Tip parked. |
| 2026-09-13 | Grok `cursor-grok-4.6-xhigh` | typed-rpc-platform re-review after four fixes | **NOT PASS** | Prior #7/#8 fixed. CI Any + Body 227/16/lint OK. Req 3 FAIL: editor `uv run mypy` 2 errors / 8 files. Composer on main; Tip parked. |
| 2026-09-13 | Grok `cursor-grok-4.6-xhigh` | typed-rpc-platform editor-mypy sync | **NOT PASS** | `uv run mypy` 11 files OK; Body 229. Sync-into-pyproject still serializes every op. Prefer static globs. Composer on main; Tip parked. |
| 2026-09-13 | Grok `cursor-grok-4.6-xhigh` | typed-rpc-platform static globs | **PASS** | Req 1–8. Body 228 / editor mypy 0 errors / discovery tests 10. Native 16 not re-run. Composer landed MCP `374a59b` + parent `07d75f0497`. |
| 2026-09-13 | Composer 2.5 | campaign roundup | paused | Tip unpark + parallel op forks interrupted. Worktrees inventoried; docs committed; PR CI not green. Merge left to Rchiemstra. |
