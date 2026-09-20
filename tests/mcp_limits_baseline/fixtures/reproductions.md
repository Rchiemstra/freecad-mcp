# Minimal ordered MCP-call reproductions — run-20260916-mcp-limits

Every step below is a typed MCP action. `ctx` is omitted for brevity (pass `{}`).
No arbitrary code is involved in any reproduction.

---

## R-01 · D-03 `revolve_feature` always fails ('Symmetric')

**Fixture**
1. `create_document {name: "ReproRevolve"}`
2. `body_create {doc_name: "ReproRevolve", body_name: "B"}`
3. `sketch_create {doc_name: "ReproRevolve", sketch_name: "S", body_name: "B", attach_to: "XY_Plane"}`
4. `sketch_add_rectangle {doc_name: "ReproRevolve", sketch_name: "S", x1: -10, y1: -10, x2: 10, y2: 10}`

**Trigger**
5. `revolve_feature {doc_name: "ReproRevolve", sketch_name: "S", revolve_name: "Rev", angle: 360, axis: "Y_Axis", body_name: "B"}`

**Expected** a `PartDesign::Revolution` in body `B`, or a geometry-kernel error about the profile.
**Actual** `status: failed` — `execute_code failed in document 'ReproRevolve': 'PartDesign.Feature' object has no attribute 'Symmetric'`
**State after** `get_document_tree` shows body `B` with only sketch `S`; no `Rev`, no orphan, document healthy.
**Reproduced** 3/3 (angle 360 / 180 / 90; axis Y_Axis / Y_Axis / Z_Axis; `symmetric` default and explicit `false`).
**Root cause (from the error)** the tool sets `Symmetric` unconditionally; `PartDesign::Revolution` in FreeCAD 26.3.0 does not expose it.

---

## R-02 · D-04 `sketch_create` hangs when attaching to a **Body**-level face

**Fixture**
1. `create_document {name: "ReproAttach"}`
2. `body_create {doc_name: "ReproAttach", body_name: "NB"}`
3. `sketch_create {doc_name: "ReproAttach", sketch_name: "NS", body_name: "NB", attach_to: "XY_Plane"}`
4. `sketch_add_rectangle {doc_name: "ReproAttach", sketch_name: "NS", x1: -10, y1: -10, x2: 10, y2: 10}`
5. `pad_feature {doc_name: "ReproAttach", sketch_name: "NS", pad_name: "P1", length: 10, body_name: "NB", strict: true}`
6. `find_faces {doc_name: "ReproAttach", object_name: "NB", type: "Plane", normal_approx: {x:0,y:0,z:1}}`  → returns `FaceN` **on the Body**

**Trigger (fails)**
7. `sketch_create {doc_name: "ReproAttach", sketch_name: "S_Fail", body_name: "NB", attach_to: "NB:Face1"}`

**Expected** sketch attached to that face (this is the natural composition of steps 6 and 7).
**Actual** `status: failed` after 30 s — *"Timed out after 30.0s waiting for FreeCAD GUI response while executing; execution continues in FreeCAD and may keep the GUI unresponsive."*
**State after** `get_document_tree`: no `S_Fail`; nothing partial. Subsequent GUI calls are rejected until the hung request finishes.

**Control (succeeds instantly, same document, same face geometry)**
8. `sketch_create {doc_name: "ReproAttach", sketch_name: "S_OK", body_name: "NB", attach_to: "P1:Face1"}` → `succeeded`

**Reproduced** 3/3 with `NB:Face1`, `NB:Face2`, `NB:Face3` in a 15-object document in which every other
mutation returned in under one second.

---

## R-03 · D-05 `bounding_box` / `measure_volume` fail on `App::Link`

**Fixture** (continues R-02, or any document with a solid-bearing object `NB`)
1. `create_object {doc_name: "ReproAttach", obj_type: "App::Link", obj_name: "L1", obj_properties: {"LinkedObject": "NB", "Placement": {"Base": {"x": 50, "y": 0, "z": 0}}}}`

**Trigger**
2. `bounding_box {doc_name: "ReproAttach", obj_name: "L1"}`
3. `measure_volume {doc_name: "ReproAttach", obj_name: "L1"}`

**Expected** per the `bounding_box` docstring: *"Link-safe: follows `App::Link` to the linked solid when
needed and applies `getGlobalPlacement()` once"* — a world-frame bbox / volume of the linked solid.
**Actual** both: `FreeCAD RPC error -32000: 'App.DocumentObject' object has no attribute 'getGlobalPlacement'`
**Working alternative** `inspect_geometry {doc_name: "ReproAttach", object_name: "L1"}` returns
`local_bbox` and `global_bbox` correctly.
**Reproduced** 3/3 across two documents (`Collar_B` in `MCPLimit_Shaft`, `Link_NB` in `MCPLimit_Neg`).

---

## R-04 · D-06 `get_object` reports success for a nonexistent object

1. `create_document {name: "ReproLookup"}`
2. `get_object {doc_name: "ReproLookup", obj_name: "NoSuchObject"}`

**Expected** a failure, as `pad_feature` and `measure_volume` give for missing names.
**Actual** `{"status": "succeeded", "data": {"value": null}, "layers": {"tool_status": "succeeded"}}`
**Impact** an agent branching on `status` cannot distinguish "absent" from "fetched".

---

## R-05 · D-08 negative pad length is silently reversed

1..4 as R-02 fixture steps 1–4 (body `NB`, sketch `NS`, rectangle 20×20).
5. `pad_feature {doc_name: ..., sketch_name: "NS", pad_name: "PadNeg", length: -10, body_name: "NB", strict: true}`

**Expected** rejection of an out-of-contract value (the tool has a dedicated `reversed_dir` flag), or
documented behaviour.
**Actual** `succeeded`, `bbox: [-10,-10,-10, 10,10,0]`, `volume_after_mm3: 4000` — i.e. a pad in −Z.
**Contrast** `length: 0` is correctly rejected: *"Cannot create a pad with a total length of zero."*

---

## R-06 · D-07 self-intersecting profile is padded instead of refused

1..3 as R-02 fixture steps 1–3, with sketch name `NS_Bowtie`.
4. `sketch_add_polyline {doc_name: ..., sketch_name: "NS_Bowtie", closed: true, points: [{"x":-6,"y":-6},{"x":6,"y":6},{"x":6,"y":-6},{"x":-6,"y":6}]}`
5. `pad_feature {doc_name: ..., sketch_name: "NS_Bowtie", pad_name: "PadBowtie", length: 5, body_name: "NB", strict: true}`

**Expected** rejection — `pad_feature` documents a pre-build check for a closed, well-formed profile.
**Actual** `succeeded`, `material_delta_mm3: 360` (the two triangular prisms, 2 × ½·12·6 · 5).
`validate_geometry` afterwards: `is_valid: true`, `is_closed: true`, `check_ok: true`.
**Impact** degenerate input is silently reinterpreted rather than refused. Benign here, but the
validation promise in the docstring is not met.

---

## R-07 · D-01 timed-out mutation that actually committed (load-dependent)

This one requires a document large enough to push GUI mutations past the 30 s client budget —
in this run, roughly 38+ objects (6 PartDesign bodies with their Origin groups).

**Fixture** build `MCPLimit_Shaft` as in `REPORT.md` §2 (or load
`models/MCPLimit_Shaft_v1.FCStd`) until the document holds ~38 objects.

**Trigger** any GUI-mode mutation, e.g.
`set_expression {doc_name: "MCPLimit_Shaft", object_name: "Pad_SupA", prop_path: "Length", expression: "<<P>>.bearing_width"}`

**Expected** either a success, or a failure that means nothing was applied.
**Actual** `status: failed` — *"Timed out after 30.0s … execution continues in FreeCAD …"*
**Then** `list_expressions {doc_name: "MCPLimit_Shaft", object_name: "Pad_SupA"}` →
`[{"prop": "Length", "expression": "<<P>>.bearing_width"}]` — **the mutation committed.**

**Why this is unrecoverable in-band:** `get_request_status` and `cancel_request` both return
*"This operation requires authenticated RPC v2"* in this runtime, so there is no handle to ask what
happened. The only correct client behaviour today is: never retry, and re-inspect the specific object
with a read-only tool (`list_expressions`, `get_sketch_diagnostics`, `get_document_tree`,
`measure_volume`, `bounding_box`) before continuing.

**Observed ratio in this run:** 10 of 11 timed-out mutations had committed; 1 had not
(`sketch_create` with a Body-face attachment — R-02, which is a different defect).
A separate `set_expression` that failed with *"Remote end closed connection without response"* had
**not** committed, confirming that failure text does not predict the outcome either way.
