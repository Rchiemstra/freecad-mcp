# FreeCAD MCP — feedback problem status

Reconciliation of the problems raised in the feedback doc against the fixes
implemented in this MCP server. "MCP-side" means the guardrail lives in the MCP
operations/templates (no FreeCAD core change required); "core" means an upstream
FreeCAD source change.

Tests: every fix has unit tests in `tests/test_diagnostics.py` (and
`tests/e2e/test_p*_*.py` spec tests) plus e2e tests under `tests/e2e/test_i*_*.py`
and `tests/e2e/test_mx_helpers.py`, run headlessly via Docker
(`.github/workflows/mcp-tests.yml`).

## Problems and fixes

| ID | Problem | Root cause | Fix | Where | Upstream |
|----|---------|-----------|-----|-------|----------|
| P1 | Cross-body datum drops the source body's non-identity placement. | Attacher wrote a global attachment placement into the attached object's local `Placement` when the object lived inside a body/group. | Core fix converts the calculated global attachment placement back into the attached object's parent group coordinates before storing it; MCP diagnostics/preflight still report risky cross-body setups. | core + MCP-side | Fixed locally; keep MCP guardrails until upstreamed. |
| P2 | Pad extrudes the wrong way silently. | Pad direction handling (#16539). | Pad/pocket append a silent-build assertion that checks the extrusion `Direction` is parallel to the profile sketch normal (I2); xfail repro `test_p2_*` arbitrates. | MCP-side | #16539 in fork; not merged upstream — file/track. |
| P3 | Rotated "Deactivated" datum drops the rotation. | Attachment `Deactivated` path (#19571). | `preview_attachment` reports the angle diff; recipe "XY_Plane + AttachmentOffset instead of rotated datum" (M2); xfail repro `test_p3_*` arbitrates. | MCP-side | #19571 open upstream — file/track. |
| P4 | Sketch solver errors swallowed. | — | `get_sketch_diagnostics` surfaces conflicting/redundant/malformed constraints + solver message. | MCP-side | n/a |
| P5 | Assembly joint moves a body and breaks cross-body datums. | Joints move bodies. | `create_assembly_joint` PREFLIGHT WARNING when a referenced component's body has cross-body datums attached (M4). | MCP-side | n/a |
| P6 | `removeObject(body)` orphans owned children. | By design per `Body.cpp`. | `delete_object` refuses to silently orphan: `recursive=True` removes dependents first, `force=True` reports orphans left, else refuses and lists them (I5). | MCP-side | #26356/#29034 — file/track. |
| P7 | Loft/Sweep silent geometry errors. | — | Loft/sweep/helical_sweep append the silent-build bbox/shape assertion (I2). | MCP-side | n/a |
| P8 | `Part.Circle` `Direction`/`Normal` alias confusion. | Conic API. | Core fix applied in `ConicPyImp.cpp` (P3-8); `face_normal`/`edge_axis` derive the vector from geometry, not the attribute (M6). | core + MCP-side | file/track the `ConicPyImp.cpp` change. |
| P9 | No documented Assembly solve API. | `Assembly.solveAssembly` missing. | `solve_assembly` tool + RPC method try `assembly.solve()`, then `JointObject.solveIfAllowed`, then recompute (I9). | MCP-side | file/track the solve API docs. |
| P10 | `get_view` cannot return a viewable image (headless/TechDraw). | No GUI view. | `get_view` returns `ImageContent` when available, else a compact geometric state (I10); `capture_state`/`geometric_diff` provide richer text-only diffs. | MCP-side | n/a |
| P11 | Constraint signature mismatch. | `addConstraint` forms. | Constructor supports the forms; `sketch_add_constraint` semantics; xfail repro `test_p11_*` arbitrates. | MCP-side | file/track if repro still fails. |
| P12 | No cheap snapshot/restore for experimentation. | — | `snapshot`/`restore` tools + RPC methods, in-process ring buffer of last 5 states (I7). | MCP-side | n/a |

## Improvements summary

* **I1** `preview_attachment` — cross-body attachment diagnostic.
* **I2** Silent-build assertions on pad/pocket/loft/sweep/helical_sweep.
* **I3** Auto-surfaced recompute log on every mutating tool.
* **I4** `find_faces`/`find_edges` by geometry (no fragile indices).
* **I5** Recursive/warned `delete_object`.
* **I6** Cross-body pre-flight warning on datum/binder creation.
* **I7** `snapshot`/`restore` + RPC methods.
* **I9** `solve_assembly` MCP tool + RPC method.
* **I10** Structured geometric diff (`capture_state`/`geometric_diff`).
* **I11** Per-request GUI response queues + `check_rpc_sync` nonce probe prevent and detect stale responses after an RPC timeout.
* **M2** Recipes in `create_datum_plane`/`sketch_create` docstrings.
* **M3** `placement_audit`.
* **M4** Joint↔PartDesign cross-body warning.
* **M5** `relink_references`.
* **M6** `face_normal`/`edge_axis` helpers.

## Still-open upstream issues to file/track

These are FreeCAD core behaviours the MCP now works around; the underlying
upstream tickets should be filed or tracked so the guardrails can eventually be
retired:

1. **P2** — Pad direction (#16539); confirm the fork fix and upstream it.
2. **P3** — Rotated "Deactivated" datum drops the rotation (#19571).
3. **P6** — `removeObject(body)` orphans owned children (#26356 / #29034).
4. **P8** — `Part.Circle` `Direction`/`Normal` alias (`ConicPyImp.cpp` change).
5. **P9** — Document the Assembly solve API (`assembly.solve` /
   `JointObject.solveIfAllowed`).
6. **P11** — `Sketcher::Constraint` constructor/addConstraint signature forms.

> Filing these GitHub issues is an explicit, external action and is left to the
> maintainer; this doc tracks them so the MCP guardrails can be retired once
> FreeCAD fixes them.
