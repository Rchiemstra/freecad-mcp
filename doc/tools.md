# Tool reference

This inventory covers **174 registered MCP tools**. Names are exact, including
deprecated and retired compatibility entries. Each name links to its registration
function. Use your client’s `tools/list` result for the current argument schema
and full tool description. Availability also depends on the connected FreeCAD build,
optional workbenches, worker executable and external solvers.

[Back to the README](../README.md#full-tool-reference).

The groups follow the [capability manifests](../src/freecad_mcp/capabilities/subject_manifest_index.py).
The [registration runtime](../src/freecad_mcp/capabilities/registration_runtime.py)
loads their tool modules; the [registry contract test](../tests/mcp/test_mcp_tool_registry_contract_snapshot.py)
checks the live registry against the [174-tool snapshot](../tests/fixtures/mcp_tool_registry_contract_snapshot.json).

Prefer typed modelling tools for changes. `execute_code` is an escape hatch;
read-only worker code operates on a snapshot. `run_transaction` is retired, and
`execute_code_async` is deprecated and blocked in lease enforcement.

For result status and validation, see [structured results](structured-results.md),
[document health](document-health.md) and [rollback coverage](transactions-and-rollback.md).

## Documents, objects and Python (8)

[Manifest](../src/freecad_mcp/capabilities/core/manifest.py).

| Tool | Purpose |
| --- | --- |
| [`create_document`](../src/freecad_mcp/generated/capabilities/register_modules/tools_core_document.py#L25) | Create a new FreeCAD document. |
| [`create_object`](../src/freecad_mcp/generated/capabilities/register_modules/tools_core_document.py#L52) | Create a supported FreeCAD object type; use PartDesign tools for an editable mechanical part. |
| [`delete_object`](../src/freecad_mcp/generated/capabilities/register_modules/tools_core_objects.py#L166) | Delete an object without silently orphaning its dependents. |
| [`edit_object`](../src/freecad_mcp/generated/capabilities/register_modules/tools_core_objects.py#L27) | Set properties on an existing FreeCAD object. |
| [`execute_code`](../src/freecad_mcp/generated/capabilities/register_modules/tools_core_execute.py#L75) | Execute Python in a live document, or analyse a snapshot with `read_only=true` in a FreeCADCmd worker. |
| [`execute_code_async`](../src/freecad_mcp/generated/capabilities/register_modules/tools_core_execute.py#L25) | Deprecated background execution; blocked in lease enforcement. Use `execute_code` worker mode for read-only analysis. |
| [`inspect_references`](../src/freecad_mcp/generated/capabilities/register_modules/tools_core_objects.py#L65) | Inspect link/subelement properties without evaluating their owner shapes. |
| [`repair_references`](../src/freecad_mcp/generated/capabilities/register_modules/tools_core_objects.py#L106) | Replace broken link or subelement properties in one transaction; recompute is optional. |

## Recompute and undo history (6)

[Manifest](../src/freecad_mcp/capabilities/document_history/manifest.py).

| Tool | Purpose |
| --- | --- |
| [`close_document`](../src/freecad_mcp/generated/capabilities/register_modules/tools_document_history.py#L138) | Close an open FreeCAD document and free its memory. |
| [`get_mutation_readiness`](../src/freecad_mcp/generated/capabilities/register_modules/tools_document_history.py#L29) | Report pending transactions, recompute work, collaboration barriers and rollback quarantine before editing. |
| [`get_recompute_log`](../src/freecad_mcp/generated/capabilities/register_modules/tools_document_history.py#L108) | Return the recompute state of every object in a document. |
| [`recompute_document`](../src/freecad_mcp/generated/capabilities/register_modules/tools_document_history.py#L43) | Force FreeCAD to recompute all objects in a document. |
| [`redo`](../src/freecad_mcp/generated/capabilities/register_modules/tools_document_history.py#L89) | Redo the previously undone operation in a FreeCAD document. |
| [`undo`](../src/freecad_mcp/generated/capabilities/register_modules/tools_document_history.py#L65) | Undo the last operation in a FreeCAD document. |

## Bodies, spreadsheets and expressions (14)

[Manifest](../src/freecad_mcp/capabilities/parametric/manifest.py).

| Tool | Purpose |
| --- | --- |
| [`body_create`](../src/freecad_mcp/generated/capabilities/register_modules/tools_parametric_body.py#L29) | Create a PartDesign Body through the required native mutation API. |
| [`body_set_tip`](../src/freecad_mcp/generated/capabilities/register_modules/tools_parametric_body.py#L50) | Set a Body's Tip to a feature (keeps the PartDesign history tip correct). |
| [`clear_expression`](../src/freecad_mcp/generated/capabilities/register_modules/tools_parametric_sheet_b.py#L80) | Clear an expression binding on an object property. |
| [`diagnose_parametric`](../src/freecad_mcp/generated/capabilities/register_modules/tools_parametric_body.py#L138) | Report invalid objects, expression problems and sketch constraint summaries. |
| [`get_sketch_diagnostics`](../src/freecad_mcp/generated/capabilities/register_modules/tools_parametric_body.py#L160) | Return solver diagnostics for a Sketcher sketch. |
| [`list_expressions`](../src/freecad_mcp/generated/capabilities/register_modules/tools_parametric_sheet_b.py#L103) | List ExpressionEngine bindings on an object. |
| [`set_expression`](../src/freecad_mcp/generated/capabilities/register_modules/tools_parametric_sheet_b.py#L45) | Bind a FreeCAD expression to an object property. |
| [`sketch_attach`](../src/freecad_mcp/generated/capabilities/register_modules/tools_parametric_body.py#L73) | Attach a sketch to an origin plane or a face. |
| [`sketch_edit_constraint`](../src/freecad_mcp/generated/capabilities/register_modules/tools_parametric_body.py#L108) | Edit a dimensional constraint by stable `name` (preferred) or index. |
| [`spreadsheet_create`](../src/freecad_mcp/generated/capabilities/register_modules/tools_parametric_sheet_a.py#L27) | Create a Spreadsheet::Sheet for parametric dimensions. |
| [`spreadsheet_get_cells`](../src/freecad_mcp/generated/capabilities/register_modules/tools_parametric_sheet_a.py#L84) | Read spreadsheet cell contents and evaluated values. |
| [`spreadsheet_list_aliases`](../src/freecad_mcp/generated/capabilities/register_modules/tools_parametric_sheet_b.py#L27) | List all aliases on a spreadsheet as `{alias: address}`. |
| [`spreadsheet_set_alias`](../src/freecad_mcp/generated/capabilities/register_modules/tools_parametric_sheet_a.py#L111) | Set a spreadsheet cell alias (e.g. A1 → Wall). |
| [`spreadsheet_set_cells`](../src/freecad_mcp/generated/capabilities/register_modules/tools_parametric_sheet_a.py#L53) | Set spreadsheet cell values (and optional aliases) in batch. |

## Sketch geometry and constraints (35)

[Manifest](../src/freecad_mcp/capabilities/sketch/manifest.py).

| Tool | Purpose |
| --- | --- |
| [`sketch_add_arc`](../src/freecad_mcp/generated/capabilities/register_modules/tools_sketch_primitives.py#L114) | Add a circular arc to a sketch. |
| [`sketch_add_arc_of_ellipse`](../src/freecad_mcp/generated/capabilities/register_modules/tools_sketch_curves_a2.py#L73) | Add an arc of an ellipse to a sketch. |
| [`sketch_add_bezier`](../src/freecad_mcp/generated/capabilities/register_modules/tools_sketch_curves_a.py#L157) | Add a Bezier curve defined by control poles to a sketch. |
| [`sketch_add_bspline`](../src/freecad_mcp/generated/capabilities/register_modules/tools_sketch_curves_a.py#L66) | Add a B-spline defined by control points (poles) to a sketch. |
| [`sketch_add_bspline_through_points`](../src/freecad_mcp/generated/capabilities/register_modules/tools_sketch_curves_a.py#L116) | Add a B-spline that interpolates (passes through) a set of points. |
| [`sketch_add_circle`](../src/freecad_mcp/generated/capabilities/register_modules/tools_sketch_primitives.py#L73) | Add a full circle to a sketch. |
| [`sketch_add_constraint`](../src/freecad_mcp/generated/capabilities/register_modules/tools_sketch_create_1.py#L146) | Add constraints to an existing Sketcher sketch. |
| [`sketch_add_ellipse`](../src/freecad_mcp/generated/capabilities/register_modules/tools_sketch_curves_a2.py#L26) | Add a full ellipse to a sketch. |
| [`sketch_add_geometry`](../src/freecad_mcp/generated/capabilities/register_modules/tools_sketch_create_1.py#L87) | Add geometry elements to an existing Sketcher sketch. |
| [`sketch_add_line`](../src/freecad_mcp/generated/capabilities/register_modules/tools_sketch_primitives.py#L27) | Add a line segment to a sketch. |
| [`sketch_add_parametric_curve`](../src/freecad_mcp/generated/capabilities/register_modules/tools_sketch_curves_b.py#L74) | Sample Python expressions to create a sketch curve. |
| [`sketch_add_polyline`](../src/freecad_mcp/generated/capabilities/register_modules/tools_sketch_curves_a.py#L27) | Add joined line segments with coincident constraints. |
| [`sketch_add_rectangle`](../src/freecad_mcp/generated/capabilities/register_modules/tools_sketch_primitives.py#L163) | Add a rectangle with four joined line segments. |
| [`sketch_add_regular_polygon`](../src/freecad_mcp/generated/capabilities/register_modules/tools_sketch_curves_b.py#L27) | Add a regular polygon to a sketch (edges joined by coincident constraints). |
| [`sketch_add_slot`](../src/freecad_mcp/generated/capabilities/register_modules/tools_sketch_curves_a2.py#L126) | Add a slot (oblong) shape to a sketch. |
| [`sketch_constrain_coincident`](../src/freecad_mcp/generated/capabilities/register_modules/tools_sketch_constraints_1.py#L28) | Constrain two sketch points to be coincident (share the same position). |
| [`sketch_constrain_distance`](../src/freecad_mcp/generated/capabilities/register_modules/tools_sketch_constraints_1.py#L137) | Add a distance (length) constraint to a line or between two points. |
| [`sketch_constrain_equal`](../src/freecad_mcp/generated/capabilities/register_modules/tools_sketch_constraints_2.py#L27) | Constrain two geometry elements to have equal length or radius. |
| [`sketch_constrain_horizontal`](../src/freecad_mcp/generated/capabilities/register_modules/tools_sketch_constraints_1.py#L73) | Constrain a line to be horizontal. |
| [`sketch_constrain_parallel`](../src/freecad_mcp/generated/capabilities/register_modules/tools_sketch_constraints_2.py#L62) | Constrain two lines to be parallel. |
| [`sketch_constrain_perpendicular`](../src/freecad_mcp/generated/capabilities/register_modules/tools_sketch_constraints_2.py#L97) | Constrain two lines to be perpendicular (90°). |
| [`sketch_constrain_radius`](../src/freecad_mcp/generated/capabilities/register_modules/tools_sketch_constraints_1.py#L185) | Constrain the radius of a circle or arc. |
| [`sketch_constrain_tangent`](../src/freecad_mcp/generated/capabilities/register_modules/tools_sketch_constraints_2.py#L132) | Constrain two curves (or a curve and a line) to be tangent. |
| [`sketch_constrain_vertical`](../src/freecad_mcp/generated/capabilities/register_modules/tools_sketch_constraints_1.py#L105) | Constrain a line to be vertical. |
| [`sketch_create`](../src/freecad_mcp/generated/capabilities/register_modules/tools_sketch_create_1.py#L26) | Create a new Sketcher sketch in FreeCAD. |
| [`sketch_delete_constraint`](../src/freecad_mcp/generated/capabilities/register_modules/tools_sketch_create_2.py#L25) | Delete one or more constraints from a Sketcher sketch. |
| [`sketch_delete_geometry`](../src/freecad_mcp/generated/capabilities/register_modules/tools_sketch_create_2.py#L65) | Delete one or more geometry items from a Sketcher sketch. |
| [`sketch_extend`](../src/freecad_mcp/generated/capabilities/register_modules/tools_sketch_curves_b2.py#L67) | Extend a sketch curve by a given increment. |
| [`sketch_fillet`](../src/freecad_mcp/generated/capabilities/register_modules/tools_sketch_curves_b2.py#L143) | Add a fillet arc between two sketch curves. |
| [`sketch_import_points`](../src/freecad_mcp/generated/capabilities/register_modules/tools_sketch_curves_b.py#L137) | Import a list of 2-D points as individual point geometry elements. |
| [`sketch_offset`](../src/freecad_mcp/generated/capabilities/register_modules/tools_sketch_curves_b2.py#L181) | Offset sketch geometry inward or outward. |
| [`sketch_split`](../src/freecad_mcp/generated/capabilities/register_modules/tools_sketch_curves_b2.py#L105) | Split a sketch curve into two pieces at the given point. |
| [`sketch_symmetry`](../src/freecad_mcp/generated/capabilities/register_modules/tools_sketch_curves_b2.py#L222) | Apply symmetry to a set of sketch elements about a symmetry axis. |
| [`sketch_toggle_construction`](../src/freecad_mcp/generated/capabilities/register_modules/tools_sketch_curves_b.py#L172) | Toggle one or more sketch geometry elements between normal and construction mode. |
| [`sketch_trim`](../src/freecad_mcp/generated/capabilities/register_modules/tools_sketch_curves_b2.py#L29) | Trim a sketch curve at the given point (nearest intersection). |

## Solid features and booleans (14)

[Manifest](../src/freecad_mcp/capabilities/features/manifest.py).

| Tool | Purpose |
| --- | --- |
| [`boolean_difference`](../src/freecad_mcp/generated/capabilities/register_modules/tools_features_boolean.py#L61) | Subtract shape2 from shape1 (Part::Cut). |
| [`boolean_intersection`](../src/freecad_mcp/generated/capabilities/register_modules/tools_features_boolean.py#L96) | Compute the Boolean intersection (common) of two shapes (Part::Common). |
| [`boolean_union`](../src/freecad_mcp/generated/capabilities/register_modules/tools_features_boolean.py#L26) | Compute the Boolean union (fuse) of two shapes (Part::Fuse). |
| [`chamfer_feature`](../src/freecad_mcp/generated/capabilities/register_modules/tools_features_advanced_b.py#L121) | Add a chamfer to edges of an existing solid (PartDesign::Chamfer). |
| [`fillet_feature`](../src/freecad_mcp/generated/capabilities/register_modules/tools_features_advanced_b.py#L79) | Add a fillet to edges of an existing solid (PartDesign::Fillet). |
| [`helical_sweep_feature`](../src/freecad_mcp/generated/capabilities/register_modules/tools_features_advanced_b.py#L26) | Sweep a profile along a helix (PartDesign::AdditiveHelix). |
| [`linear_pattern_feature`](../src/freecad_mcp/generated/capabilities/register_modules/tools_features_basic_1.py#L158) | Repeat an existing PartDesign feature along a straight direction. |
| [`loft_feature`](../src/freecad_mcp/generated/capabilities/register_modules/tools_features_advanced_a.py#L73) | Loft through two or more sketch sections (PartDesign::AdditiveLoft). |
| [`mirror_feature`](../src/freecad_mcp/generated/capabilities/register_modules/tools_features_basic_2.py#L84) | Mirror an existing PartDesign feature across a plane. |
| [`pad_feature`](../src/freecad_mcp/generated/capabilities/register_modules/tools_features_basic_1.py#L26) | Extrude (pad) a closed sketch profile into a 3-D solid (PartDesign::Pad). |
| [`pocket_feature`](../src/freecad_mcp/generated/capabilities/register_modules/tools_features_basic_1.py#L92) | Cut (pocket) a closed sketch profile into an existing solid (PartDesign::Pocket). |
| [`polar_pattern_feature`](../src/freecad_mcp/generated/capabilities/register_modules/tools_features_basic_2.py#L25) | Repeat an existing PartDesign feature around an axis. |
| [`revolve_feature`](../src/freecad_mcp/generated/capabilities/register_modules/tools_features_advanced_a.py#L26) | Revolve a closed sketch profile around an axis (PartDesign::Revolution). |
| [`sweep_feature`](../src/freecad_mcp/generated/capabilities/register_modules/tools_features_advanced_a.py#L114) | Sweep a profile sketch along a path sketch (PartDesign::AdditivePipe). |

## Gears (5)

[Manifest](../src/freecad_mcp/capabilities/gear/manifest.py).

| Tool | Purpose |
| --- | --- |
| [`check_gear_pair`](../src/freecad_mcp/generated/capabilities/register_modules/tools_gear_2.py#L69) | Verify that two gears form a valid meshing pair. |
| [`compute_gear_geometry`](../src/freecad_mcp/generated/capabilities/register_modules/tools_gear_2.py#L25) | Compute standard gear geometry parameters without creating geometry. |
| [`create_helical_gear`](../src/freecad_mcp/generated/capabilities/register_modules/tools_gear_1.py#L183) | Create a helical gear (involute profile + AdditiveHelix twist). |
| [`create_involute_gear`](../src/freecad_mcp/generated/capabilities/register_modules/tools_gear_1.py#L111) | Create an involute spur gear. |
| [`create_spur_gear`](../src/freecad_mcp/generated/capabilities/register_modules/tools_gear_1.py#L26) | Create a spur gear from a Sketcher tooth profile and Pad. |

## Assemblies and joints (4)

[Manifest](../src/freecad_mcp/capabilities/assembly/manifest.py).

| Tool | Purpose |
| --- | --- |
| [`create_assembly`](../src/freecad_mcp/generated/capabilities/register_modules/tools_assembly.py#L27) | Create a built-in Assembly workbench assembly object. |
| [`create_assembly_grounded_joint`](../src/freecad_mcp/generated/capabilities/register_modules/tools_assembly.py#L54) | Ground an assembly component through the headless Assembly API. |
| [`create_assembly_joint`](../src/freecad_mcp/generated/capabilities/register_modules/tools_assembly.py#L85) | Create a built-in Assembly joint from two component subelement references. |
| [`solve_assembly`](../src/freecad_mcp/generated/capabilities/register_modules/tools_assembly.py#L154) | Solve an assembly and return its method and status; rejected solves return an error. |

## Containers, paths and attachment references (16)

[Manifest](../src/freecad_mcp/capabilities/partdesign/manifest.py).

| Tool | Purpose |
| --- | --- |
| [`build_path_wire`](../src/freecad_mcp/generated/capabilities/register_modules/tools_partdesign_a2.py#L88) | Build a Part wire from sketch geometry and optional bridge segments. |
| [`create_datum_plane`](../src/freecad_mcp/generated/capabilities/register_modules/tools_partdesign_a.py#L116) | Create a PartDesign datum plane for assembly reference workflows. |
| [`create_part_container`](../src/freecad_mcp/generated/capabilities/register_modules/tools_partdesign_a.py#L27) | Create an App::Part assembly container. |
| [`create_placement_binder`](../src/freecad_mcp/generated/capabilities/register_modules/tools_partdesign_b2.py#L83) | Create a binder from a Body subpath and report placement diagnostics. |
| [`create_placement_datum`](../src/freecad_mcp/generated/capabilities/register_modules/tools_partdesign_b2.py#L117) | Create a datum plane from a Body subpath and report local and global placement diagnostics. |
| [`create_subshape_binder`](../src/freecad_mcp/generated/capabilities/register_modules/tools_partdesign_a.py#L81) | Create a PartDesign SubShapeBinder with placement validation. |
| [`edge_axis`](../src/freecad_mcp/generated/capabilities/register_modules/tools_partdesign_b2.py#L27) | Return an edge’s global axis or direction and centre. |
| [`face_normal`](../src/freecad_mcp/generated/capabilities/register_modules/tools_partdesign_b.py#L170) | Return a face’s global normal and centre. |
| [`find_edges`](../src/freecad_mcp/generated/capabilities/register_modules/tools_partdesign_b.py#L115) | Find edges by geometric criteria rather than relying on fixed edge indices. |
| [`find_faces`](../src/freecad_mcp/generated/capabilities/register_modules/tools_partdesign_b.py#L60) | Find faces by geometric criteria rather than relying on fixed face indices. |
| [`get_sketch_geometry`](../src/freecad_mcp/generated/capabilities/register_modules/tools_partdesign_a2.py#L27) | Return sketch geometry endpoints, construction flags, constraints, and external refs. |
| [`move_object`](../src/freecad_mcp/generated/capabilities/register_modules/tools_partdesign_a.py#L52) | Move an object into a PartDesign Body or App::Part container. |
| [`placement_audit`](../src/freecad_mcp/generated/capabilities/register_modules/tools_partdesign_b2.py#L57) | Report Body and Part placements, global placements and cross-body datum references. |
| [`preview_attachment`](../src/freecad_mcp/generated/capabilities/register_modules/tools_partdesign_b.py#L27) | Preview an existing datum's attachment — a read-only P1 diagnostic. |
| [`sketch_add_external_projection`](../src/freecad_mcp/generated/capabilities/register_modules/tools_partdesign_a2.py#L53) | Add external geometry to a sketch with assembly-aware preflight checks. |
| [`sweep_pipe`](../src/freecad_mcp/generated/capabilities/register_modules/tools_partdesign_a2.py#L117) | Sweep a circular solid pipe along a wire path. |

## Measurement and geometry validation (9)

[Manifest](../src/freecad_mcp/capabilities/measure/manifest.py).

| Tool | Purpose |
| --- | --- |
| [`bounding_box`](../src/freecad_mcp/generated/capabilities/register_modules/tools_measure_a.py#L86) | Return the world-frame axis-aligned bounding box of a shape. |
| [`center_of_mass`](../src/freecad_mcp/generated/capabilities/register_modules/tools_measure_b.py#L107) | Return the geometric centre of mass of a solid; density and print fill are separate inputs to mass estimates. |
| [`common_volume_along_path`](../src/freecad_mcp/generated/capabilities/register_modules/tools_measure_b.py#L54) | Return per-sample overlap volumes and collision flags from a read-only worker. |
| [`get_global_shape`](../src/freecad_mcp/generated/capabilities/register_modules/tools_measure_b.py#L27) | Resolve a world-frame shape summary for solids and App::Link objects. |
| [`measure_angle`](../src/freecad_mcp/generated/capabilities/register_modules/tools_measure_a.py#L32) | Measure the angle between two edges or objects. |
| [`measure_area`](../src/freecad_mcp/generated/capabilities/register_modules/tools_measure_a.py#L51) | Measure the total surface area of a shape. |
| [`measure_distance`](../src/freecad_mcp/generated/capabilities/register_modules/tools_measure_a.py#L16) | Measure the minimum distance between two shapes. |
| [`measure_volume`](../src/freecad_mcp/generated/capabilities/register_modules/tools_measure_a.py#L66) | Measure the volume of a solid shape. |
| [`validate_geometry`](../src/freecad_mcp/generated/capabilities/register_modules/tools_measure_b.py#L131) | Validate the geometry of a shape and return diagnostic information. |

## Analysis, snapshots and reference repair (12)

[Manifest](../src/freecad_mcp/capabilities/advanced/manifest.py).

| Tool | Purpose |
| --- | --- |
| [`audit_hardcoded_dimensions`](../src/freecad_mcp/generated/capabilities/register_modules/tools_advanced_a.py#L96) | Report driving Body dimensions that lack expression bindings. |
| [`capture_state`](../src/freecad_mcp/generated/capabilities/register_modules/tools_advanced_b.py#L59) | Capture a compact geometric state for selected objects. |
| [`geometric_diff`](../src/freecad_mcp/generated/capabilities/register_modules/tools_advanced_b.py#L87) | Compare a captured geometric state with the current model. |
| [`get_dependency_graph`](../src/freecad_mcp/generated/capabilities/register_modules/tools_advanced_a.py#L146) | Return object dependencies annotated with their referencing properties. |
| [`inspect_geometry`](../src/freecad_mcp/generated/capabilities/register_modules/tools_advanced_a.py#L119) | Inspect normalised geometry in local and world coordinates. |
| [`match_subshape`](../src/freecad_mcp/generated/capabilities/register_modules/tools_advanced_a.py#L173) | Rank target subshapes by geometric similarity to a source subshape. |
| [`relink_references`](../src/freecad_mcp/generated/capabilities/register_modules/tools_advanced_b.py#L26) | Redirect references from one object to a replacement object. |
| [`restore`](../src/freecad_mcp/generated/capabilities/register_modules/tools_advanced_b2.py#L49) | Restore the latest or named snapshot by closing the current document and reopening the snapshot. |
| [`run_fem_analysis`](../src/freecad_mcp/generated/capabilities/register_modules/tools_advanced_b2.py#L78) | Run CalculiX on an existing analysis and return stress, displacement, node count and the working directory. |
| [`run_transaction`](../src/freecad_mcp/generated/capabilities/register_modules/tools_advanced_a.py#L30) | Retired. Always returns `RUN_TRANSACTION_RETIRED`; use typed modelling tools. |
| [`snapshot`](../src/freecad_mcp/generated/capabilities/register_modules/tools_advanced_b2.py#L26) | Retain a document checkpoint in a ring buffer of the last five states. |
| [`validate_movement_follow`](../src/freecad_mcp/generated/capabilities/register_modules/tools_advanced_a.py#L63) | Check whether dependent objects follow a source Body through a rigid transform. |

## Pocket, helix and document diagnostics (3)

[Manifest](../src/freecad_mcp/capabilities/diagnostics/manifest.py).

| Tool | Purpose |
| --- | --- |
| [`compare_documents`](../src/freecad_mcp/generated/capabilities/register_modules/tools_diagnostics.py#L69) | Compare two open documents (e.g. V7 vs V8) via paired geometric state diffs. |
| [`diagnose_helix`](../src/freecad_mcp/generated/capabilities/register_modules/tools_diagnostics.py#L47) | Report helix axis, profile, placement, pitch, handedness and recompute diagnostics. |
| [`diagnose_pocket`](../src/freecad_mcp/generated/capabilities/register_modules/tools_diagnostics.py#L26) | Report pocket support, profile, direction, depth and geometry diagnostics. |

## Document access, views and selection (21)

[Manifest](../src/freecad_mcp/capabilities/gui/manifest.py).

| Tool | Purpose |
| --- | --- |
| [`activate_document`](../src/freecad_mcp/generated/capabilities/register_modules/tools_gui_document_b.py#L31) | Make an already-open document the active GUI document. |
| [`animate_placement`](../src/freecad_mcp/generated/capabilities/register_modules/tools_gui_view_b.py#L93) | Animate placement keyframes or a path, capture frames and restore the starting placement. |
| [`encode_view_video`](../src/freecad_mcp/generated/capabilities/register_modules/tools_gui_view_a.py#L129) | Encode a view sequence to MP4 using system ffmpeg. |
| [`get_gui_state`](../src/freecad_mcp/generated/capabilities/register_modules/tools_gui_document_b.py#L110) | Read this MCP actor’s personal GUI context. |
| [`get_object`](../src/freecad_mcp/generated/capabilities/register_modules/tools_gui_document_a.py#L107) | Read the properties of a single document object. |
| [`get_objects`](../src/freecad_mcp/generated/capabilities/register_modules/tools_gui_document_a.py#L59) | List document objects with bounded projection and pagination. |
| [`get_parts_list`](../src/freecad_mcp/generated/capabilities/register_modules/tools_gui_document_a.py#L138) | List parts from the optional parts library addon. |
| [`get_report_view`](../src/freecad_mcp/generated/capabilities/register_modules/tools_gui_document_b.py#L129) | Read text from FreeCAD’s Report view. |
| [`get_selection`](../src/freecad_mcp/generated/capabilities/register_modules/tools_gui_document_b.py#L94) | Read this MCP actor’s personal selection. |
| [`get_view`](../src/freecad_mcp/generated/capabilities/register_modules/tools_gui_view_a.py#L26) | Capture a framed viewport screenshot; geometric state is a fallback when an image is unavailable. |
| [`insert_part_from_library`](../src/freecad_mcp/generated/capabilities/register_modules/tools_gui_document_a.py#L30) | Insert a library part into an explicit leased document. |
| [`list_documents`](../src/freecad_mcp/generated/capabilities/register_modules/tools_gui_document_a.py#L189) | Get the list of open documents in FreeCAD. |
| [`open_document`](../src/freecad_mcp/generated/capabilities/register_modules/tools_gui_document_a.py#L206) | Open a `.FCStd` project or a file handled by a registered FreeCAD import module. |
| [`recompute_and_wait`](../src/freecad_mcp/generated/capabilities/register_modules/tools_gui_document_b.py#L154) | Recompute a document and block until the GUI is idle, then report state. |
| [`refresh_view`](../src/freecad_mcp/generated/capabilities/register_modules/tools_gui_view_b.py#L27) | Force a GUI redraw after Link/shape edits; optionally touch Placement and frame. |
| [`reload_document`](../src/freecad_mcp/generated/capabilities/register_modules/tools_gui_document_a.py#L150) | Close and re-open a document to pick up external file changes. |
| [`repair_view_placements`](../src/freecad_mcp/generated/capabilities/register_modules/tools_gui_view_b.py#L71) | Reassign selected Placement values under the document's active lease. |
| [`save_view_sequence`](../src/freecad_mcp/generated/capabilities/register_modules/tools_gui_view_a.py#L87) | Capture multiple framed screenshots for motion/station review. |
| [`select_subshapes`](../src/freecad_mcp/generated/capabilities/register_modules/tools_gui_document_b.py#L68) | Set this MCP actor’s personal object or subshape selection. |
| [`set_section_view`](../src/freecad_mcp/generated/capabilities/register_modules/tools_gui_document_b.py#L174) | Enable, disable, or query the active view clipping (section) plane. |
| [`set_tree_expanded`](../src/freecad_mcp/generated/capabilities/register_modules/tools_gui_document_b.py#L43) | Expand or collapse model-tree items in the FreeCAD GUI. |

## Import, export and display (7)

[Manifest](../src/freecad_mcp/capabilities/io/manifest.py).

| Tool | Purpose |
| --- | --- |
| [`export_brep`](../src/freecad_mcp/generated/capabilities/register_modules/tools_io_export.py#L87) | Export a shape to a BREP file (OpenCASCADE native format). |
| [`export_step`](../src/freecad_mcp/generated/capabilities/register_modules/tools_io_export.py#L28) | Export shapes to a STEP file. |
| [`export_stl`](../src/freecad_mcp/generated/capabilities/register_modules/tools_io_export.py#L57) | Export shapes to an STL file (tessellated mesh). |
| [`get_document_tree`](../src/freecad_mcp/generated/capabilities/register_modules/tools_io_export.py#L158) | Return a compact document and container tree. |
| [`import_brep`](../src/freecad_mcp/generated/capabilities/register_modules/tools_io_import.py#L49) | Import a BREP file into an existing FreeCAD document. |
| [`import_step`](../src/freecad_mcp/generated/capabilities/register_modules/tools_io_import.py#L25) | Import a STEP file into an existing FreeCAD document. |
| [`set_color`](../src/freecad_mcp/generated/capabilities/register_modules/tools_io_export.py#L117) | Set the display colour and transparency of an object. |

## Document leases and verified saves (10)

[Manifest](../src/freecad_mcp/capabilities/lease/manifest.py).

| Tool | Purpose |
| --- | --- |
| [`acquire_document_lock`](../src/freecad_mcp/generated/capabilities/register_modules/tools_lease_acquire_a.py#L43) | Acquire an exclusive renewable document write lease. |
| [`adopt_dirty_document`](../src/freecad_mcp/generated/capabilities/register_modules/tools_lease_acquire_a.py#L70) | Adopt existing unsaved changes into the verified lease-v2 lifecycle. |
| [`finalize_document_edit`](../src/freecad_mcp/generated/capabilities/register_modules/tools_lease_lifecycle.py#L124) | Save or Save As, verify the native save and model validation, then release a clean lease. |
| [`get_document_lock`](../src/freecad_mcp/generated/capabilities/register_modules/tools_lease_acquire_a.py#L96) | Read redacted effective local and foreign lease status for one document. |
| [`list_document_locks`](../src/freecad_mcp/generated/capabilities/register_modules/tools_lease_acquire_a.py#L114) | List redacted local, foreign, stale, error and dirty-recovery lease records. |
| [`release_document_lock`](../src/freecad_mcp/generated/capabilities/register_modules/tools_lease_acquire_b.py#L58) | Release a lease only after a clean saved or restored state is verified. |
| [`save_document`](../src/freecad_mcp/generated/capabilities/register_modules/tools_lease_lifecycle.py#L41) | Perform native Save and verify a stable FCStd hash, archive structure and metadata. |
| [`save_document_as`](../src/freecad_mcp/generated/capabilities/register_modules/tools_lease_lifecycle.py#L62) | Perform native Save As and verify the file; existing destinations are refused by default. |
| [`save_document_copy`](../src/freecad_mcp/generated/capabilities/register_modules/tools_lease_lifecycle.py#L91) | Save and verify a copy without moving the canonical savepoint; recovery copies retain model-state limits. |
| [`update_document_lock`](../src/freecad_mcp/generated/capabilities/register_modules/tools_lease_acquire_b.py#L43) | Update bounded task and progress metadata without changing write authority. |

## Runtime identity and request recovery (5)

[Manifest](../src/freecad_mcp/capabilities/runtime/manifest.py).

| Tool | Purpose |
| --- | --- |
| [`cancel_request`](../src/freecad_mcp/generated/capabilities/register_modules/tools_runtime_control.py#L167) | Request cooperative cancellation for an authenticated RPC request. |
| [`check_rpc_sync`](../src/freecad_mcp/generated/capabilities/register_modules/tools_runtime_control.py#L63) | Round-trip a nonce through the GUI queue to verify response synchronisation. |
| [`claim_acquisition_result`](../src/freecad_mcp/generated/capabilities/register_modules/tools_runtime_control.py#L144) | Recover custody of a lost or pending acquire, adopt or create lease credential. |
| [`get_request_status`](../src/freecad_mcp/generated/capabilities/register_modules/tools_runtime_control.py#L112) | Query a timed-out or long-running authenticated request without replaying it. |
| [`get_runtime_info`](../src/freecad_mcp/generated/capabilities/register_modules/tools_runtime_info.py#L279) | Report exact MCP, addon, FreeCAD, RPC, and isolated-profile identity. |

## Transforms (3)

[Manifest](../src/freecad_mcp/capabilities/transform/manifest.py).

| Tool | Purpose |
| --- | --- |
| [`rotate`](../src/freecad_mcp/generated/capabilities/register_modules/tools_transform.py#L64) | Rotate an object around a specified axis. |
| [`scale`](../src/freecad_mcp/generated/capabilities/register_modules/tools_transform.py#L114) | Scale an object non-uniformly along the three axes. |
| [`translate`](../src/freecad_mcp/generated/capabilities/register_modules/tools_transform.py#L26) | Translate (move) an object by a displacement vector. |

## Headless worker control (2)

[Manifest](../src/freecad_mcp/capabilities/worker/manifest.py).

| Tool | Purpose |
| --- | --- |
| [`cancel_worker_job`](../src/freecad_mcp/generated/capabilities/register_modules/tools_worker.py#L44) | Cancel a pending worker job or terminate the active worker process tree. |
| [`get_worker_status`](../src/freecad_mcp/generated/capabilities/register_modules/tools_worker.py#L22) | Report isolated FreeCADCmd availability and whether a worker job is active. |
