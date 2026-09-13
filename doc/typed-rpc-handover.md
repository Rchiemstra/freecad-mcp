# Typed RPC campaign — handover (2026-09-13 roundup)

Standalone handover for Rchiemstra or a new agent with **no chat history**. Read this first, then `doc/feature_typed-rpc_progress.md` for the full audit trail.

**Models (local only):** implementer `composer-2.5`; reviewer `cursor-grok-4.6-xhigh`. Forbidden: Fast, Cloud, Auto, or substitute models.

**Final merge:** Rchiemstra only. Do not merge PRs from agent sessions.

---

## Status at roundup

| Area | Verdict | Notes |
| --- | --- | --- |
| **typed-rpc-platform** | **PASS** (Grok req 1–8) | Landed on `feature/typed-rpc`. Static mypy globs, `TYPED_RPC_HANDLER` discovery, `commit_native_mutation`, discoverable `ci/check_*_contract.py` gates. |
| **`body_create` reference** | **PASS** (prior cycles) | `ci/qualify_body_create.py` — 228 focused tests at platform landing; native 16 (last Grok run). |
| **`body_set_tip`** | **NOT PASS** | Native flaky 13/14–14/14; area 5 fixed. Unpark onto platform SHA started then interrupted. |
| **Parallel ops** (`sketch_create`, `sketch_attach`, `pad_feature`) | **NOT PASS** | Worktrees forked; setup only, no typed implementation files. |
| **PR CI** | **Not green** | Both PRs mergeable **CONFLICTING/DIRTY**. Required checks not passing. |

Campaign is **paused**. No further op migrations were started in the roundup session.

---

## SHAs, PRs, and CI

| Repo | Branch | HEAD | PR | CI (roundup) |
| --- | --- | --- | --- | --- |
| MCP `tools/mcp/freecad-mcp` | `feature/typed-rpc` | `374a59b7f8e74e6f15c6326db00abdd5fb0f3f38` | https://github.com/Rchiemstra/freecad-mcp/pull/17 | **No checks reported**; merge **CONFLICTING/DIRTY** |
| Parent `D:/code/FreeCAD` | `feature/typed-rpc` | `07d75f049719b48d72590d07452be6f67732bd4d` | https://github.com/Rchiemstra/FreeCAD/pull/53 | Labeler **SUCCESS** only; Prepare/Ubuntu/Lint and Woodpecker **not scheduled**; merge **CONFLICTING/DIRTY** |

**Merge order:** MCP PR #17 first, then parent PR #53 (submodule pointer). Rchiemstra must resolve conflicts and get required CI green before merge.

**Older reference baselines** (do not confuse with current HEAD):

| Baseline | SHA |
| --- | --- |
| Parent at `body_create` qualify | `b253505340ce45d0d6720bc9894f0e063e6196e5` |
| MCP at `body_create` qualify | `c4fa4f5562e2319606945efc7c1aa0767ad5f9d9` |

---

## Worktrees (honest inventory)

```
D:/code/FreeCAD                   07d75f0497 [feature/typed-rpc]
D:/code/FreeCAD-wt-body-set-tip   07d75f0497 [feature/typed-rpc-body-set-tip]
D:/code/FreeCAD-wt-pad-feature    07d75f0497 [feature/typed-rpc-pad-feature]
D:/code/FreeCAD-wt-sketch-attach  07d75f0497 [feature/typed-rpc-sketch-attach]
D:/code/FreeCAD-wt-sketch-create  07d75f0497 [feature/typed-rpc-sketch-create]
```

| Worktree | Branch | Parent HEAD | MCP checkout | State |
| --- | --- | --- | --- | --- |
| `D:/code/FreeCAD` | `feature/typed-rpc` | `07d75f0497` | `374a59b` on `feature/typed-rpc` | Platform landed; tracker + docs |
| `D:/code/FreeCAD-wt-body-set-tip` | `feature/typed-rpc-body-set-tip` | `07d75f0497` (reset from older `d0d82b`) | `374a59b` on `feature/typed-rpc-body-set-tip` | Tip-only files **restored unstaged**; unpark **incomplete**; **NOT PASS** |
| `D:/code/FreeCAD-wt-sketch-create` | `feature/typed-rpc-sketch-create` | `07d75f0497` | `374a59b` on `feature/typed-rpc-sketch-create` | Setup only; **no typed files**; **NOT PASS** |
| `D:/code/FreeCAD-wt-sketch-attach` | `feature/typed-rpc-sketch-attach` | `07d75f0497` | `374a59b` on `feature/typed-rpc-sketch-attach` | Setup only; **NOT PASS** |
| `D:/code/FreeCAD-wt-pad-feature` | `feature/typed-rpc-pad-feature` | `07d75f0497` | `374a59b` (detached; **may not be an isolated MCP git worktree**) | Setup only; **NOT PASS** |

### Tip worktree leftover files (unstaged, do not commit as-is)

MCP worktree has unstaged Tip implementation artifacts, e.g.:

- `addon/FreeCADMCP/_shared/protocol/body_set_tip_contract.py`
- `addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/body_set_tip.py`
- `addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/body_set_tip_mutation.py`
- `ci/check_body_set_tip_contract.py`, `ci/qualify_body_set_tip.py`
- `src/freecad_mcp/operations/parametric_ops/body_set_tip_legacy.py` (+ modified `body_set_tip.py`)
- tests and `tests/typecheck/body_set_tip_protocol.py`

These reflect prior Composer work reviewed **NOT PASS** (native flake). Unpark must re-apply onto platform patterns (`commit_native_mutation`, no `commit_body_set_tip_mutation`).

---

## What is proven vs not

### Proven (platform + Body)

1. **Generic native commit** — `commit_native_mutation` on `CollaborationAPI` / `CadCollaborators` / `CompatibilityMutationAPI`; `commit_body_create_mutation` kept for Body.
2. **RPC discovery** — `TYPED_RPC_HANDLER` in leaf modules; `bind_typed_rpc_handlers` / `discover_typed_rpc_handlers`; no per-op edits to `cad_methods.py` / `facade_bindings.py` for new ops.
3. **Mypy without per-op pyproject edits** — static globs + `follow_imports=normal` + `disallow_any_explicit` on `cad_methods_ops.*` / `parametric_ops.*`; dummy `Any` fails editor mypy.
4. **Discoverable contract CI** — `ci/run_contract_checks.py` runs every `ci/check_*_contract.py`; Woodpecker calls it from parent `ci/woodpecker/freecad-mcp-lint.sh`.
5. **`body_create`** — reference implementation; Grok PASS across mutation policy, contracts, JSON-RPC, native matrix (16 tests).

### Not proven / incomplete

1. **`body_set_tip`** — focused 161 / Body regression OK; native `--native` **flaky** (13/14–14/14). Do not merge.
2. **Parallel ops** — worktrees exist; zero typed implementation.
3. **PR merge readiness** — conflicts + CI not green on both PRs.
4. **MCP catalog regen** — new tool names still need `manifest.py` + `python scripts/generate_capability_shadow.py` (do not hand-edit `generated/**`).

---

## How to resume

### 1. Rchiemstra: land platform PRs

1. Resolve merge conflicts on https://github.com/Rchiemstra/freecad-mcp/pull/17
2. Get MCP CI green; merge #17
3. Update parent submodule pointer; resolve https://github.com/Rchiemstra/FreeCAD/pull/53 conflicts
4. Get Woodpecker + required parent CI green; merge #53

### 2. Unpark `body_set_tip` (first op)

Work in `D:/code/FreeCAD-wt-body-set-tip` only.

1. Confirm parent @ platform SHA and MCP submodule on `feature/typed-rpc-body-set-tip` @ merged MCP main (or platform SHA).
2. Re-implement using **platform patterns only**:
   - `{op}_contract.py` (vendored pair)
   - `cad_methods_ops/{op}.py` with `TYPED_RPC_HANDLER`
   - `cad_methods_ops/{op}_mutation.py` calling `collaborators.commit_native_mutation`
   - `parametric_ops/{op}.py` client
   - `ci/qualify_{op}.py` + `ci/check_{op}_contract.py`
   - `tests/typecheck/{op}_protocol.py`
   - **No** `commit_body_set_tip_mutation` in `collaboration_api.py`
   - **No** edits to `pyproject.toml`, Woodpecker, `sketch_public.py`, `cad_methods.py` for registration
3. Fix native flake: stable `_model_state` for FeaturePython proxies; require 3 consecutive green `--native` runs.
4. Grok review (`cursor-grok-4.6-xhigh`); commit MCP first, then parent gate lines if any.
5. Do **not** merge until PASS.

### 3. Parallel ops (after Tip PASS or in separate worktrees)

Fork pattern (already done for three ops):

- Parent worktree: `feature/typed-rpc-{op_name}`
- MCP submodule branch: `feature/typed-rpc-{op_name}` @ platform MCP SHA
- **Add new files only** — no edits to platform files listed above

Suggested order after Tip: `sketch_create` → `sketch_attach` → `pad_feature` (PartDesign core chain).

---

## Commands

Run from MCP root (`tools/mcp/freecad-mcp`) unless noted.

### Body reference qualification

```bash
uv run python ci/qualify_body_create.py
uv run python ci/qualify_body_create.py --native   # needs freecad-ci-mcp:24.04-phase1
```

### Mypy (editor + CI use same pyproject)

```bash
uv run mypy --no-incremental
```

### Contract discovery gate

```bash
uv run python ci/run_contract_checks.py
```

### Woodpecker lint (from parent root)

```bash
docker run --rm -v D:/code/FreeCAD:/work -w /work python:3.12 sh ci/woodpecker/freecad-mcp-lint.sh
```

### Native image

- Docker image: `freecad-ci-mcp:24.04-phase1`
- Host needs `build_docker` libs on `LD_LIBRARY_PATH` / `PYTHONPATH` (see `ci/qualify_body_create.py --native` and architecture docs)

### Tip qualification (when unparked)

```bash
uv run python ci/qualify_body_set_tip.py
uv run python ci/qualify_body_set_tip.py --native
```

### Git workflow (every landed change)

1. Commit **MCP submodule** first (`tools/mcp/freecad-mcp`)
2. Commit **parent** submodule pointer (+ any parent-only CI files)
3. Push MCP `origin/feature/typed-rpc`, then parent `origin/feature/typed-rpc`
4. Never `--no-verify`, never force push, never update git config

---

## Do-not list

- **Do not merge** PRs #17 / #53 (Rchiemstra only).
- **Do not** use Fast, Cloud, or Auto models.
- **Do not** hand-edit `src/freecad_mcp/generated/**` or `addon/FreeCADMCP/generated/**`.
- **Do not** add per-op `commit_{op}_mutation` methods to `collaboration_api.py` — use `commit_native_mutation`.
- **Do not** add per-op RPC registration in `sketch_public.py`, `cad_methods.py`, or `facade_bindings.py` — use `TYPED_RPC_HANDLER`.
- **Do not** edit `pyproject.toml` or Woodpecker for each new op (static globs + contract discovery).
- **Do not** claim PASS without Grok review and complete evidence (especially native `--native`).
- **Do not** commit Tip worktree dirty state without a fresh PASS review.
- **Do not** create new worktrees in roundup; use existing inventory above.

---

## Documentation map

| File | Purpose |
| --- | --- |
| `tools/mcp/freecad-mcp/doc/feature_typed-rpc_progress.md` | Full audit trail (moved from `.idea/`; canonical) |
| `tools/mcp/freecad-mcp/doc/typed-rpc-handover.md` | This file |
| `doc/typed-rpc-handover.md` | Parent copy + pointer to MCP docs |
| `ci/qualify_body_create.py` | Body reference acceptance runner |
| `ci/discover_typed_slice.py` | Mypy discovery helpers |
| `ci/run_contract_checks.py` | Woodpecker contract gate runner |

---

## Leftover state (honest)

- Platform code is landed locally and pushed; **PRs are not merge-ready** (conflicts, CI gaps).
- Four op worktrees exist; only Tip has partial unstaged implementation (NOT PASS).
- Three parallel op worktrees are empty shells (setup only).
- `pad_feature` MCP submodule may be on detached `374a59b` rather than a proper isolated worktree — verify before use.
- Progress tracker no longer lives in gitignored `.idea/`; use `doc/feature_typed-rpc_progress.md`.
