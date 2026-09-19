# FreeCAD MCP — action-surface limit campaign

Run ID: `run-20260916-mcp-limits`  ·  Date: 2026-09-16
Agent-selected arbitrary-code calls (`execute_code` / `execute_code_async` / `run_transaction` /
worker code jobs / macros / Python console): **ZERO**.
All modelling, inspection, validation, persistence and recovery below was done through typed MCP
actions only. Bash was used solely to read git/proc metadata and to write these Markdown/JSON files.

---

## 0. Environment and runtime identity (Section 2)

| Item | Value |
|---|---|
| FreeCAD checkout | `/home/msi/FreeCAD`, branch `FreeCAD-start`, HEAD `962f18d5ed1acfbbb91bab33582a176a36f3d2ca` |
| Dirty tree | 2 untracked files under `tests/standalone/` (unrelated) |
| MCP submodule | `tools/mcp/freecad-mcp` @ `bcce4abc78073ccbe0f81116ec72540a4c8a37a1` (`heads/fix/solve-assembly-typed-rpc-binding`), clean |
| Live binary | pid 316969 → `/home/msi/FreeCAD/build/release/bin/FreeCAD` (verified via `/proc/<pid>/exe`) |
| MCP server | pid 317891 → `/home/msi/FreeCAD/tools/mcp/freecad-mcp/.venv/bin/freecad-mcp` |
| FreeCAD | 26.3.0, revision 48664 (Git) |
| MCP / addon | 0.2.0 / 0.2.0, `build_id` `freecad-mcp-0.2.0+unknown` |
| RPC | protocol_version 1 (addon) vs 2 (MCP) → `compatibility.compatible = false` |
| Profile | `instance_id` "unknown", `path_fingerprint` 92e111a6… |

**The connected runtime does correspond to this checkout** — established out of band from
`/proc/316969/exe`. It could NOT be established from the MCP surface itself: `get_runtime_info`
reports `git_commit: "unknown"`, `git_dirty: null`, `instance_id: "unknown"` (F-05,
OBSERVABILITY_GAP). Treat "this branch was validated" as true only with that external evidence.

Documents used (all disposable, created through MCP): `MCPLimit_Calib`, `MCPLimit_Sentinel`
(sentinel), `MCPLimit_StepRT`, `MCPLimit_Shaft`, `MCPLimit_Neg`, `MCPLimit_Scale`,
`MCPLimit_CalibR2`, `MCPLimit_CalibR3`. No pre-existing user document was opened, modified or closed.
Total MCP calls: **272** (budget 1000). Peak live test objects: well under 250 real objects
(plus one 250-element link array). Max outstanding requests: 4.

---

## 1. FINDINGS, most severe first

### D-01 — FAIL (high) · Timed-out mutations frequently **did** commit; the tool reports failure
`Timed out after 30.0s waiting for FreeCAD GUI response while executing; execution continues in
FreeCAD…` is returned as `status: "failed"`. Independent re-inspection afterwards shows the mutation
**was applied** in most cases.

Observed, with the verification that resolved each one:

| # | Call | Reported | Actually applied? | Verified by |
|---|---|---|---|---|
| T1 | `sketch_create(attach_to="Plate:Face6")` | failed/timeout | **NO** | `get_document_tree` — no such object |
| T2 | `sketch_add_constraint(Horizontal geo2)` on `S_SupA` | failed/timeout | **YES** | `get_sketch_diagnostics`: constraints 11→12, dof 0 |
| T3 | `set_expression(S_SupA.Constraints.sup_w)` | failed/timeout | **YES** | `list_expressions` |
| T4 | `set_expression(S_SupA.Constraints.sup_z0)` | failed/timeout | **YES** | `list_expressions` |
| T5 | `set_expression(Pad_SupA.Length)` | failed/timeout | **YES** | `list_expressions` |
| T6 | `sketch_create(S_SupB)` | failed/timeout | **YES** | `get_document_tree` |
| T7 | `sketch_add_constraint` ×11 on `S_SupB` | failed/timeout | **YES** (all 11) | `get_sketch_diagnostics`: 11 constraints |
| T8 | `pad_feature(Pad_SupB)` | failed/timeout | **YES** | `bounding_box` 34×7×50 |
| T9 | `pocket_feature(Bore_B)` | failed/timeout | **YES** | `measure_volume` 9239.071 |
| T10 | `create_object(App::Link Collar_B)` | failed/timeout | **YES** | `inspect_geometry` |
| T11 | `spreadsheet_set_cells(base_length/width)` | failed/timeout | **YES** | `bounding_box` 140×90×6 |

Ratio: **10 of 11 timed-out mutations committed.** A client that retries on failure will
double-apply. The documented recovery path does not exist here: `get_request_status` and
`cancel_request` are among the 21 tools disabled by the RPC mismatch (D-02), so after a timeout the
outcome is `UNKNOWN_OUTCOME` until the agent re-inspects each affected object by hand.
Related: one `set_expression` failed with `Remote end closed connection without response` and did
**not** apply (`list_expressions` empty) — so connection-drop failures are indeterminate in the other
direction too.
Reproducibility: 11/11 occurrences of the timeout message in this run; the "did commit" behaviour
10/11.

### D-02 — CAPABILITY_GAP (high) · RPC protocol mismatch disables 21 actions, incl. all of save/undo/reopen
`get_runtime_info` → `"RPC protocol mismatch: MCP=2, addon=1"`, `compatible: false`.
Unavailable (`requires_authenticated_rpc_v2`): `activate_document, animate_placement,
cancel_request, capture_view_sequence, capture_view_sequence_to_disk, finalize_document_edit,
get_active_screenshot, get_gui_state, get_report_view, get_request_status, get_selection,
open_document, redo, refresh_view, reload_document, repair_view_placements, save_document,
select_subshapes, set_section_view, set_tree_expanded, undo`.
Verified live: `save_document` → *"This operation requires authenticated RPC v2"*;
`open_document` → `error_code: LEASE_PROTOCOL_REQUIRED`; `undo` → same v2 error.
**Consequence:** the Section 5C *save → close → reopen → compare* cycle and *undo/redo around
successful operations* are **impossible through MCP in this runtime**. Recovery is still possible via
`snapshot`/`restore` (D-09, works), and durability via the degraded `save_document_as`.

### D-03 — FAIL (high) · `revolve_feature` is broken on this FreeCAD build
Every call fails with `'PartDesign.Feature' object has no attribute 'Symmetric'`. The tool sets a
`Symmetric` property that `PartDesign::Revolution` does not expose in FreeCAD 26.3.0.
Reproduced **3/3** with angle 360/180/90, axes Y/Y/Z, `symmetric` default and explicit `false`.
No orphan object is left behind. Revolve is therefore unreachable; the shaft in the test assembly had
to be built as a padded circular section instead.

### D-04 — FAIL (high) · `sketch_create(attach_to="<Body>:FaceN")` hangs for 30 s and creates nothing
Attaching to a **Body**-level face hangs; attaching to the same face via the **feature** works
instantly. Reproduced **3/3** (`NB:Face1`, `NB:Face2`, `NB:Face3`) in a 15-object document where
every other mutation returned in under a second, with the control
(`Pad_Bowtie:Face1`) succeeding immediately in the same document — so this is a deterministic
defect, not load. It matters because `find_faces` is normally run **on the Body** and returns
`FaceN`, so the natural composition of the two documented tools is the failing one.

### D-05 — FAIL (medium) · `bounding_box` and `measure_volume` crash on `App::Link`
`'App.DocumentObject' object has no attribute 'getGlobalPlacement'`, although `bounding_box`'s own
docstring says *"Link-safe: follows `App::Link` to the linked solid … and applies
`getGlobalPlacement()`"* and `measure_volume` returns a `used_linked_object` field.
Reproduced 3/3 (`bounding_box` ×2, `measure_volume` ×1) on two different links in two documents.
`inspect_geometry` handles the same link correctly (returns local and global bbox), so the workaround
exists but the documented contract of the two measurement tools is wrong.

### D-06 — FAIL (medium) · `get_object` on a nonexistent object returns `status: "succeeded"`
`get_object(doc="MCPLimit_Neg", obj="NoSuchObject")` → `status: "succeeded"`, `data.value: null`.
An agent that branches on `status` treats a missing object as a successful lookup. By contrast
`pad_feature` and `measure_volume` on missing names fail cleanly.

### D-07 — CAPABILITY_GAP (medium) · profile validation does not reject self-intersecting profiles
A closed bow-tie polyline `(-6,-6)→(6,6)→(6,-6)→(-6,6)→close` was **accepted** by `pad_feature`
(which documents a pre-build check for "a closed profile"). Result: +360 mm³, exactly the two
triangular prisms, and `validate_geometry` reports a valid closed solid (`check_ok: true`).
Not corrupting, but the operation silently reinterprets degenerate input instead of refusing it.

### D-08 — FAIL (low) · negative `length` silently reinterpreted as a reversed pad
`pad_feature(length=-10)` succeeded, producing bbox z ∈ [−10, 0] and 4000 mm³. The tool has an
explicit `reversed_dir` parameter for that intent; accepting a negative length is undocumented
aliasing of an out-of-contract value. (`length=0` **is** correctly rejected:
*"Cannot create a pad with a total length of zero."*)

### D-09 — OBSERVABILITY_GAP (medium) · transactions/rollback are not in force
Every mutation response carries `transaction.status: "unavailable"`, `enabled: false`,
`rollback_policy: "none"`, `transaction_coverage: "partial"`/`"unavailable"`. The per-tool
transactional rollback described in the tool docs is therefore **not active** in this runtime.
Mitigating observation: despite that, **every** rejected operation observed in this campaign left no
partial object — atomicity came from FreeCAD's own recompute rejection, verified by
`get_document_tree` after each failure (no `SlotMirrorY`, no `Rev_*`, no `Pocket_Miss`,
no `Fillet_Huge`, no `S_FaceAttach*`).

### D-10 — OBSERVABILITY_GAP (medium) · no view capture at all
Every `pad_feature`/`pocket_feature` returns
`presentation_warning: "Screenshot capture returned no image after the feature committed."`
`get_active_screenshot` / `get_view` path is disabled by D-02. All visual confirmation in this
campaign is numeric (volume, bbox, face/edge counts, `geometric_diff`).

### D-11 — OBSERVABILITY_GAP (low) · `get_objects` has no projection or pagination
A 10-object document produced a ~15 000-token response (full property dump per object, including
`Shape` repr and view properties). At the 250-object tier this single inspector would exceed any
practical agent context. `get_document_tree` is the usable alternative and should be the documented
default.

### D-12 — FAIL (low) · `spreadsheet_set_cells` reports `alias: null` for aliases it did set
First bulk call set four aliases via `set_alias`; the response listed `{"address":"B1","alias":null}`
for every cell. `spreadsheet_list_aliases` then proved all four exist. Addressing by `alias` instead
echoes correctly.

### D-13 — INFO · dedicated actions are internally generated Python, not native RPC
Telemetry field `execution_category: "generated_internal_execute"` appears on
`spreadsheet_list_aliases`, `get_sketch_diagnostics`, `find_faces`, `find_edges`, `measure_volume`,
`bounding_box`, `validate_geometry`, `get_document_tree`, `capture_state`, `geometric_diff`,
`audit_hardcoded_dimensions`, `export_step`, `import_step`, `sketch_add_*`, `linear_pattern_feature`,
`translate`, `fillet_feature` — with `code_sha256`, `call_families` and `ast_pattern_hash`.
Read-only inspectors run `"mode": "worker"` against a read-only snapshot; mutators run `"mode": "gui"`.
This is permitted (internal templates behind a dedicated action) and is recorded here as required:
**MCP action coverage in this report is not evidence of native-RPC implementation.**
`run_transaction` is explicitly retired (`RUN_TRANSACTION_RETIRED`).

### D-14 — CAPABILITY_GAP (low) · no array-layout action
`App::Link` with `ElementCount: 250` is creatable via `create_object`, but there is no exposed action
to set per-element placements, so the 250 instances are co-located
(`inspect_geometry` global bbox dx = 89 mm).

---

## 2. What the agent successfully built, using MCP actions only

**Calibration plate (Section 3) — PASS, exact.**
Spreadsheet `Dims` (4 aliased parameters) → PartDesign `Body` → sketch on `XY_Plane` →
4 lines + 12 constraints (dof 0 after closing constraint) → named dimensional constraints bound to
the sheet by `set_expression` → `Pad` (length bound to `Dims.plate_thk`) → top face located by
geometry (`find_faces type=Plane normal≈+Z center≈(0,0,8)` → `Face6`) → second sketch attached to
that face → circle constrained to the sketch origin, `Diameter` bound to `Dims.hole_dia` → through
`Pocket`.

Tolerances declared before checking: volume ±1e-6 relative, linear ±1e-9 mm.

| Quantity | Expected | Measured (`measure_volume` / `bounding_box` / `validate_geometry`) | Verdict |
|---|---|---|---|
| Volume before pocket | 9 600 mm³ | 9 600.000000 | PASS |
| Volume after pocket | 9 600 − 200π = 8 971.681469 | **8 971.681469** | PASS |
| Bounding box | 40 × 30 × 8 | 40.0 × 30.0 × 8.0 | PASS |
| Solid / validity | 1 valid closed solid | `is_valid`, `is_closed`, `check_ok`, 7 faces, 15 edges | PASS |
| Body membership / Tip | Tip = `Pocket_Hole` | Tip = `Pocket_Hole`, `solid_count` 1 | PASS |
| Hole concentric & through | axis at origin, z 0→8 | cylinder face r=5, global centre (0, 0, 4) | PASS |
| Sentinel document | unchanged | `dirty_after[MCPLimit_Sentinel] = false` on every call; 0 objects at end | PASS |

**Parametric update — PASS.** `Dims.plate_len` 40 → 50 through `spreadsheet_set_cells`, then
`recompute_and_wait`: bbox 50 × 30 × 8, volume **11 371.681469** = 12 000 − 200π. The face-attached
hole sketch and its pocket survived the change; no rebuild, no broken references, all objects
`Up-to-date`. Reverted to 40 afterwards.

**Shaft-support assembly (Section 4) — built and parameter-driven.**
Document `MCPLimit_Shaft`, spreadsheet `P` with **17 aliases**, and these PartDesign bodies with live
feature histories:

| Body | History | Verified |
|---|---|---|
| `BasePlate` | sketch → `Pad_Base` (length = `P.base_thickness`) → slot sketch on discovered top face → `Pocket_Slot` → `SlotRowX` (LinearPattern ×2) | 57 600 mm³ padded; one slot removes 457.646 mm³ = 8×6 + π·3², four slots → **55 769.416** = 57 600 − 4×457.646 |
| `Support_A` | sketch on `XZ_Plane` (12 constraints, dof 0, 4 expressions) → `Pad_SupA` symmetric (= `P.bearing_width`) → bore sketch (3 expressions) → `Bore_A` symmetric | 11 900 mm³ → **9 239.071** after bore = 11 900 − π·11²·7 |
| `Support_B` | same chain, independently constructed | **9 239.071** — identical |
| `Shaft` | sketch on `YZ_Plane`, Ø bound to `P.shaft_diameter` → `Pad_Shaft` symmetric | 100 × 8 × 8, axis exactly at z = 40 |
| `Collar_A` | annular sketch (2 concentric circles) → `Pad_ColA` → `translate` | **1 165.154** = π(8²−4.2²)·8 |
| `Collar_B` | `App::Link` instance of `Collar_A` | placed at x −48…−40 (`inspect_geometry`) |
| `Cover` | sketch with `attachment_offset` z = 56 → `Pad_Cover` → `Fillet_Cover` r = 4 on 4 vertical edges **found by geometry** (`find_edges type=Line direction≈+Z`) | fillet committed, body valid |

Exercised: sketch attachment (planes, feature faces, attachment offsets), constrained geometry,
pad/pocket (blind, symmetric, through), linear pattern, fillet, geometry-based face **and** edge
discovery, containers/links, placement via `translate`, spreadsheet aliases and expressions,
measurement, validity, document health, dependency inspection, `audit_hardcoded_dimensions`,
`capture_state`/`geometric_diff`, STEP export/import, `snapshot`/`restore`.

**Three design changes, each verified (Section 4).**

1. **Base dimensions** `base_length` 120→140, `base_width` 80→90 → `BasePlate` bbox **140 × 90 × 6**,
   all objects `Up-to-date`. PASS.
2. **Shaft / bearing** `shaft_diameter` 8→10, `bearing_outer_diameter` 22→26 → `Shaft` bbox
   y ∈ [−5, 5], z ∈ [35, 45] (Ø10) and `Support_A` top z 56→**58**
   (= 40 + 26/2 + 5). PASS for every expression-bound feature. **`Support_B` and `Cover` did not
   follow** — see "honest limitations" below.
3. **Support spacing / slot layout** `support_spacing` 60→80, `slot_spacing_x` 90→110 →
   `geometric_diff` shows `Support_A` x 13…47 → **23…57** (= 80/2 − 34/2), `Shaft` unchanged
   (correct invariant), `Support_B` unchanged (unbound), `BasePlate` faces 22 → 26. The +4 faces are
   real and correct: the patterned slot now lands at x = 65 and breaks out of the x = 70 plate edge.
   `validate_geometry` confirms the plate is still **one valid closed solid**
   (73 868.418 mm³, `check_ok: true`) — the change produced a questionable *design*, not broken
   *geometry*, and the tools detected it. PASS (intended change + invariants both verified).

**STEP round-trip — PASS.** `export_step` of the calibration body → `import_step` into a fresh
document → volume **8 971.681469** and bbox 40 × 30 × 8, identical to the source. As expected for
STEP, the PartDesign history does not survive; only the solid was compared.

**Saved artifacts (all written through MCP, sha256 from the tool's own file evidence):**

| File | sha256 |
|---|---|
| `models/MCPLimit_Calib.FCStd` | `31a862d9b95407e66cf71d6de8ea2d6076a6fbba12d51b0896188edb3c20369a` |
| `models/MCPLimit_Shaft_v1.FCStd` | `92f9d792ba8370b495ba09c90f9a425f830b38c11686d2cc7f6f25fe8a03f110` |
| `models/MCPLimit_Shaft_v2_after_changes.FCStd` | `f0364116015ae7c06691eca971180d5e47cbde58593f7053f5e9bac5e756683b` |
| `models/MCPLimit_Neg_fixture.FCStd` | `c56f7a4db51be58dc96bb8832d1082bd138cb849d953173e0b133ff020754998` |
| `exports/calib_plate.step`, `exports/shaft_support_v1.step` | written and re-imported / verified |

---

## 3. Negative and recovery tests (Section 5)

| Case | Expectation from the schema/contract | Result | Outcome |
|---|---|---|---|
| N-01 `get_object` nonexistent | clean rejection | `status: succeeded`, value null | **FAIL** (D-06) |
| N-02 `pad_feature` nonexistent sketch + body | rejection | *"Sketch 'NoSuchSketch' not found."* | PASS_EXPECTED_REJECTION |
| N-03 any tool, nonexistent document | rejection | `NameError: Unknown document` (raw Python text, `error_code: null`) | PASS_EXPECTED_REJECTION |
| N-04 stale handle after `close_document` | rejection | `NameError: Unknown document 'MCPLimit_StepRT'` | PASS_EXPECTED_REJECTION |
| N-05 redundant constraints (batch of 12) | rejection, nothing applied | rejected, naming redundant indices; `constraint_count` still **0** | PASS_EXPECTED_REJECTION |
| N-06 underconstrained sketch (dof 16, then dof 1) | **accepted** — valid intermediate state | accepted, pad succeeded | PASS (correctly not refused) |
| N-07 open profile pad | rejection | *"Sketch profile is not pad-ready"*, pre-build, nothing created | PASS_EXPECTED_REJECTION |
| N-08 self-intersecting (bow-tie) profile pad | rejection expected | **accepted**, valid solid, +360 mm³ | **CAPABILITY_GAP** (D-07) |
| N-09 zero-length pad | rejection | *"Cannot create a pad with a total length of zero."* | PASS_EXPECTED_REJECTION |
| N-10 negative-length pad | rejection or documented behaviour | accepted as reversed pad | **FAIL** (D-08) |
| N-11 pocket that misses the solid | rejection | *"Pocket_Miss did not change the body's material volume"* — material-delta post-check | PASS_EXPECTED_REJECTION |
| N-12 excessive fillet (r = 50 on a 20 mm body) | rejection | *"Fillet not possible on selected shapes"*, no orphan | PASS_EXPECTED_REJECTION |
| N-13 mirror of a pattern | rejection (FreeCAD semantics) | *"Only additive and subtractive features can be transformed"*, no orphan `SlotMirrorY` | PASS_EXPECTED_REJECTION |
| N-14 delete object with dependents | refusal listing dependents | refused, listed `Pad_Bowtie`, `Pad_Neg`, told to use `recursive`/`force` | PASS_EXPECTED_REJECTION |
| N-15 `delete_object(recursive=true)` | deletes leaves-first | deleted `Pad_Bowtie`, `Pad_Neg`, `NS` | PASS |
| N-16 `snapshot` → destructive delete → `restore` | full recovery | restored; volume back to **4 360.0**, Tip `Pad_Bowtie`, `tip_is_member: true`, 6 members | PASS |
| N-17 explicit doc A while doc B active | explicit target wins | all writes landed in the named document; `active_document` stayed `MCPLimit_Sentinel` | PASS |
| N-18 `open_document` | — | `LEASE_PROTOCOL_REQUIRED` | CAPABILITY_GAP (D-02) |
| N-19 `undo` | — | requires authenticated RPC v2 | CAPABILITY_GAP (D-02) |
| N-20 back-pressure after a timeout | reject new work | *"FreeCAD GUI is still executing a request that timed out; new GUI work is rejected until it finishes"* | PASS (good safety property) |

Error-class separation observed: **client/schema rejection** (pydantic validation, e.g. the missing
`datum_name` on `preview_attachment`); **protocol rejection** (`LEASE_PROTOCOL_REQUIRED`,
"requires authenticated RPC v2"); **operation/pre-check error** ("not pad-ready", "did not change the
body's material volume"); **geometry-kernel failure** ("Fillet not possible on selected shapes",
"Cannot create a pad with a total length of zero"); **environment/transport failure** (30 s GUI
timeout, "Remote end closed connection", "RPC endpoint rejected the JSON-RPC request").
None of these was produced by the client blocking the call on the MCP side except the pydantic
schema errors, so the rejections above are genuine backend coverage.

After every rejection the document was re-inspected: **no orphan objects, no wrong Tip, no broken
references, no partial mutations, and no change to unrelated documents** were found at any point.

---

## 4. Measured limits (Section 6)

| Variable | Tier | Result |
|---|---|---|
| Independent objects in one document | 10 | **PASS** — all 10 present with correct placements |
| Independent objects | 50 / 100 / 250 | **NOT_TESTED** — budget/turn limited (one object per call). 10 is a tested lower bound, not the maximum |
| Link-array instances | 50 | PASS (`Array50`, `ElementCount` 50) |
| Link-array instances | 250 | **PASS** — `Array250` created and inspected (`inspect_geometry` 4.4 s); runtime stayed responsive. Instances co-located (D-14) |
| Sketch geometry in one sketch | 50 | **PASS, exact** — 50-segment closed polygon, padded: 25 066.868066 mm³ = ½·50·40²·sin(7.2°)·5 |
| Sketch geometry | 100 / 250 | NOT_TESTED |
| Parameter-edit + recompute cycles | 10 | **PASS** — 10 sequential `edit_object` length changes; final volume **75 200.604197** = exact area × 15; all 23 objects `Up-to-date`, zero recompute errors |
| Parameter-edit cycles | 25 / 50 | NOT_TESTED |
| Feature-chain depth | 5 | PASS (`BasePlate`: sketch→pad→sketch→pocket→pattern; `Support_*`: sketch→pad→sketch→pocket) |
| Feature-chain depth | 10 / 20 | NOT_TESTED |
| Concurrency, independent documents | — | 3 concurrent calls, all correct |
| Concurrency, same document | 4 outstanding writes | **PASS** — four simultaneous `create_object` calls on one document all committed with distinct names; `get_objects` confirmed all four, no lost update. Repeated twice more (8 more objects) |

### The dominant measured limit: GUI-thread latency vs the fixed 30 s client timeout

This is the real ceiling, and it is not an object-count cliff — it is a **document-size** effect on
every *mutating* call:

* In `MCPLimit_Neg` and `MCPLimit_Scale` (10–23 objects) mutations returned in well under a second;
  **zero** timeouts across ~90 mutations.
* In `MCPLimit_Shaft` at roughly **38+ objects** (6 bodies, each contributing a sketch, a feature and
  a full Origin group), essentially **every** GUI-mode mutation exceeded 30 s — 11 timeouts in a row,
  including `spreadsheet_set_cells`, `set_expression`, `sketch_create`, `pad_feature`,
  `pocket_feature` and `create_object`. The work itself completed (D-01); only the response was lost.
* Closing one unrelated document temporarily restored sub-second responses, which points at
  whole-session recompute/notification cost per mutation rather than at the edited object.
* Read-only inspectors were unaffected throughout (worker snapshot mode, 0.3–4.4 s), which is why
  every timed-out mutation could still be verified.

**Largest verified passing tier: a ~23-object document with no timeouts. First observed failing
tier: a ~38-object document, where GUI mutations exceed the 30 s budget ~100 % of the time.**
That window — under 40 objects — is small for real CAD work and is the single most important number
in this report.

---

## 5. Reproductions (Section 7)

| Scenario | Runs | Result |
|---|---|---|
| Full calibration part from a clean document | **3/3** | Identical every time: 9 600 → **8 971.68146928204**, bbox 40×30×8, Tip `Pocket_Hole` (`MCPLimit_Calib`, `MCPLimit_CalibR2`, `MCPLimit_CalibR3`) |
| Parametric update (sheet → recompute → verify) | 1 full (`plate_len` 40→50→40) + 3 design changes on the assembly | All PASS |
| `snapshot` → damage → `restore` | 1 | PASS, exact restore |
| Save → close → **reopen** → compare | 0 | **Blocked** by D-02 — `open_document`/`reload_document` unavailable. The saved FCStd files are verified on disk (sha256 + zip member check) but could not be reopened through MCP |
| D-03 `revolve_feature` | **3/3** | Fails identically |
| D-04 Body-face sketch attach | **3/3** | Hangs identically; feature-face control passes |
| D-05 link measurement | **3/3** | Fails identically |
| D-01 timeout-but-committed | 10/11 occurrences | Reproduces under load, not on demand in a small document |

Minimal ordered reproductions with exact arguments are in `reproductions.md`.

---

## 6. Honest limitations of this campaign

* **`Support_B` and `Cover` were left with hard-coded dimensions.** Design change #2 moved
  `Support_A`'s top to z = 58 while `Support_B` stayed at 56 and the `Cover` stayed at z = 56…61, so
  `Support_A` now protrudes through the cover. This is a **defect in the model I built**, not in the
  MCP surface — I bound expressions on `Support_A` and not on its twin. It is reported rather than
  quietly fixed because it is also the cleanest demonstration that `audit_hardcoded_dimensions`
  works: run on `Support_B` it correctly listed all **8** unbound driving dimensions
  (4 sketch constraints + `Pad_SupB.Length`/`Length2` + `Bore_B.Length`/`Length2`).
* Assembly **joints** (`create_assembly`, `create_assembly_joint`, `create_assembly_grounded_joint`,
  `solve_assembly`) were **NOT_TESTED**. With mutations timing out ~100 % of the time in the
  assembly-sized document, attempting to move six bodies into an `Assembly` container would have
  produced `UNKNOWN_OUTCOME` states rather than usable evidence. Assembly relationships were modelled
  by placement and links instead.
* Loft, sweep, helical sweep, gears, booleans, FEM, and the drawing/view tools were **NOT_TESTED**.
* Independent-object counts above 10, sketch geometry above 50, edit cycles above 10 and feature
  depth above 5 are **NOT_TESTED** (see the table) — the passing tiers are lower bounds.
* Latency is reported only where the tool provided it (`duration_ms` on worker-mode reads) or as the
  binary "exceeded the 30 s client budget". No wall-clock instrumentation was fabricated.
* Existing Docker/native suites were **not** run; nothing in this report comes from them.

---

## 7. Conclusions

**What the agent built with MCP actions alone.** A fully parametric calibration part matching its
analytic volume to 1e-10 relative, reproduced identically three times; and a seven-body
shaft-support assembly — base plate with a patterned four-slot mounting layout, two independently
constructed bearing supports, a shaft, two collars (one a link instance), and a filleted cover —
driven by a 17-alias spreadsheet, then put through three parameter changes that propagated correctly
through every expression-bound feature. Face and edge selection was done by geometry, never by
guessed indices. All of it, plus STEP export/import and snapshot/restore recovery, through typed
actions only.

**What was impossible without a prohibited bypass.** Native `save_document`, `open_document`,
`reload_document`, `undo`, `redo`, request status/cancellation, view capture, selection and GUI state
— 21 actions disabled by the RPC-version mismatch — and `revolve_feature`, which is broken against
this FreeCAD build. The save→close→reopen→compare recovery scenario could not be completed at all.

**Actions that returned success but produced incorrect state.** None. No action reported success and
left wrong geometry. The inverse happened repeatedly and is worse for an autonomous agent: **actions
reported failure and had in fact committed** (D-01, 10 of 11). Two further honesty defects are
reporting-only: `get_object` returning `succeeded` for a missing object (D-06), and
`spreadsheet_set_cells` reporting `alias: null` for aliases it set (D-12).

**Did failures leave FreeCAD usable and recoverable?** Yes. Across 272 calls with ~25 deliberate or
incidental failures — timeouts, kernel refusals, a dropped connection, a JSON-RPC rejection — the
session never needed a restart, the sentinel document was never touched (`dirty: false` throughout,
0 objects at the end), no orphan objects or broken references were ever found, and every damaged
state was recoverable via `snapshot`/`restore`. The back-pressure rule that rejects new GUI work
while a timed-out request is still running is a genuinely good safety property.

**What to fix first.**
1. **D-01 + D-02 together.** Either restore RPC v2 so `get_request_status`/`cancel_request` exist, or
   make the timeout path report `UNKNOWN_OUTCOME` with a re-check handle. Today a well-behaved
   retrying client corrupts models. This is the top priority.
2. **The 30 s budget vs GUI-mutation cost above ~40 objects.** Make the budget adaptive, or move
   mutations off the blocking GUI path, or stop doing whole-session work per mutation. Until then the
   interface is only reliable on documents smaller than a real assembly.
3. **D-03 `revolve_feature`** — a one-line property guard; an entire modelling operation is dead.
4. **D-04 Body-face attachment hang** — the tool pairing `find_faces(Body)` → `sketch_create` is the
   documented happy path and it is the one that hangs.
5. **D-05 link-aware measurement**, then the reporting-honesty defects D-06 / D-12, then the
   validation gaps D-07 / D-08.

**Agent-selected arbitrary-code calls: ZERO.**
