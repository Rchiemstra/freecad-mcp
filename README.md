[![MseeP.ai Security Assessment Badge](https://mseep.net/pr/neka-nat-freecad-mcp-badge.png)](https://mseep.ai/app/neka-nat-freecad-mcp)

# FreeCAD MCP

This repository is a FreeCAD MCP that allows you to control FreeCAD from Claude Desktop.

## Demo

### Design a flange

![demo](./assets/freecad_mcp4.gif)

### Design a toy car

![demo](./assets/make_toycar4.gif)

### Design a part from 2D drawing

#### Input 2D drawing

![input](./assets/b9-1.png)

#### Demo

![demo](./assets/from_2ddrawing.gif)

This is the conversation history.
https://claude.ai/share/7b48fd60-68ba-46fb-bb21-2fbb17399b48

## Install addon

FreeCAD Addon directory is
* Windows: `%APPDATA%\FreeCAD\Mod\`
* Mac:
  * FreeCAD 1.1: `~/Library/Application\ Support/FreeCAD/v1-1/Mod/`
  * FreeCAD 1.0: `~/Library/Application\ Support/FreeCAD/v1-0/Mod/`
* Linux:
  * Ubuntu: `~/.FreeCAD/Mod/` or `~/snap/freecad/common/Mod/` (if you install FreeCAD from snap)
  * Debian: `~/.local/share/FreeCAD/Mod`
  * Arch / CachyOS (FreeCAD 1.1 from `extra/freecad`): `~/.local/share/FreeCAD/v1-1/Mod/`

Please put `addon/FreeCADMCP` directory to the addon directory.

```bash
git clone https://github.com/neka-nat/freecad-mcp.git
cd freecad-mcp

# For Linux (Ubuntu/Debian)
cp -r addon/FreeCADMCP ~/.FreeCAD/Mod/

# For Linux (Arch/CachyOS, FreeCAD 1.1 from extra/freecad)
mkdir -p ~/.local/share/FreeCAD/v1-1/Mod/
cp -r addon/FreeCADMCP ~/.local/share/FreeCAD/v1-1/Mod/

# For macOS (FreeCAD 1.1)
cp -r addon/FreeCADMCP ~/Library/Application\ Support/FreeCAD/v1-1/Mod/
```

When you install addon, you need to restart FreeCAD.
You can select "MCP Addon" from Workbench list and use it.

![workbench_list](./assets/workbench_list.png)

And you can start RPC server by "Start RPC Server" command in "FreeCAD MCP" toolbar.

![start_rpc_server](./assets/start_rpc_server.png)

### Auto-Start RPC Server

By default, the RPC server must be started manually each time FreeCAD opens. To start it automatically:

1. Open the **FreeCAD MCP** menu (switch to the MCP Addon workbench first)
2. Check **Auto-Start Server**

The setting is saved to `freecad_mcp_settings.json` and persists across sessions. On the next FreeCAD launch, the RPC server will start automatically once the application finishes loading.

You can disable it at any time by unchecking **Auto-Start Server** in the same menu.

## Per-document agent leases and isolated development

FreeCAD MCP supports renewable per-document write leases. In `enforce` mode,
each cooperative mutation must belong to the authenticated MCP runtime, name an
explicit live document, carry that document's unguessable lease credential,
and pass authorization again on FreeCAD's GUI thread. Ownership, current
operation, heartbeat age, dirty state, and recovery errors remain visible in
FreeCAD between MCP calls.

The addon setting `document_lease_mode` has three compatibility levels:

- `off` preserves an existing profile whose two legacy lock booleans were
  both false. Recognized active v2 foreign sidecars still block writes.
- `observe` is the default for a newly created ordinary profile. It displays
  lease state and warnings without requiring legacy callers to acquire a
  lease.
- `enforce` requires a UUID profile identity, an owner-only authentication
  secret, protocol v2, and exact lease credentials for every mutation.

Existing settings are migrated explicitly: both legacy booleans true becomes
`enforce`, lock enabled without enforcement becomes `observe`, and all other
legacy combinations remain `off`. Malformed or unknown policy values prevent
the RPC server from starting instead of silently selecting a weaker mode.

Task descriptions stay in the addon's process-local status registry by
default; schema-v2 sidecars write an empty `task_summary`. Administrators who
accept the metadata exposure may set `persist_task_summary_in_sidecar=true`;
only a sanitized, single-line summary of at most 256 characters is then
persisted. Raw lease tokens and token fingerprints are never exposed through
public status.

A normal agent workflow acquires once, performs typed modelling calls against
the returned document session, then uses typed finalization instead of raw
Python save code:

```text
acquire_document_lock({document_name: "Bracket"}, "Body → Sketch → Pad", agent_id)
create_object(PartDesign::Body) / sketch_create / sketch_add_constraint / pad_feature
finalize_document_edit(
  {document_session_uuid: "<acquired session UUID>"},
  save_mode="save",
  validation_profile="default"
)
```

The MCP process keeps the one-time token in memory, renews it automatically,
and attaches the exact credential to each scoped mutation. A failed mutation
or save retains the lease in a visible error state for retry or local recovery;
it is never reported as a clean release.

For development beside an existing FreeCAD/MCP session, create the private
manifest-driven instance:

```powershell
python scripts/setup_isolated_profile.py
python scripts/setup_cursor_mcp_isolated.py
python scripts/start_freecad_isolated.py
```

These scripts add or update only Cursor's `freecad-isolated` entry. They do not
modify, connect to, stop, or reuse the existing `freecad` entry or default
`:9875` listener. The private profile uses a persistent random identity, a
separate owner-only 256-bit authentication secret, RPC port 9876, and
`document_lease_mode=enforce`. The launcher accepts readiness only after the
profile-secret-authenticated v2 handshake proves the exact launched PID,
profile, runtime UUID, endpoint, protocol, process start, version, and build—not
merely a successful `ping` or an unauthenticated status response.

> **Security boundary:** leases prevent accidental cooperative MCP conflicts;
> they are not a FreeCAD or Python sandbox. Python console code, macros,
> third-party C++ commands, or a malicious process running as the same OS user
> can bypass pre-mutation checks. Unexpected changes are detected and fence the
> agent, but absolute in-process immutability requires a FreeCAD core API. Keep
> RPC on loopback or use an encrypted tunnel/TLS proxy for remote access.

Documentation:

- [Lease lifecycle and GUI behavior](doc/document-leases.md)
- [Sidecar schema v2](doc/document-lease-sidecar-v2.md)
- [Isolated instance setup and manifest](doc/isolated-instance.md)
- [Crash and stale-lock recovery](doc/lease-recovery.md)
- [Security model and limitations](doc/lease-security.md)

## Setting up Claude Desktop

Pre-installation of the [uvx](https://docs.astral.sh/uv/guides/tools/) is required.

And you need to edit Claude Desktop config file, `claude_desktop_config.json`.

For user.

```json
{
  "mcpServers": {
    "freecad": {
      "command": "uvx",
      "args": [
        "freecad-mcp"
      ]
    }
  }
}
```

If you want to save token, you can set `only_text_feedback` to `true` and use only text feedback.

```json
{
  "mcpServers": {
    "freecad": {
      "command": "uvx",
      "args": [
        "freecad-mcp",
        "--only-text-feedback"
      ]
    }
  }
}
```


For developer.
First, you need clone this repository.

```bash
git clone https://github.com/neka-nat/freecad-mcp.git
```

```json
{
  "mcpServers": {
    "freecad": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/freecad-mcp/",
        "run",
        "freecad-mcp"
      ]
    }
  }
}
```

## Remote Connections

By default the RPC server does not accept remote connections and listens on
loopback. HMAC authenticates protocol-v2 messages but does not encrypt session
or lease credentials. In `enforce` mode, a plain non-loopback bind is rejected
by default. Keep FreeCAD bound to loopback and expose it through an SSH tunnel
or TLS proxy.

The legacy direct-network workflow below is available only for `off`/`observe`
profiles (or an administrator's explicit unsafe transport override). It should
be used only on a trusted, isolated network:

### 1. Enable remote connections in FreeCAD

In the **FreeCAD MCP** toolbar for an `off`/`observe` profile:

1. Check **Remote Connections** — the RPC server will bind to `0.0.0.0` (all interfaces) on the next restart. For security reasons, it only accepts connections from the IP addresses or CIDR subnets specified in the **Allowed IPs** field. By default this is `127.0.0.1`.
2. Click **Configure Allowed IPs** and enter a comma-separated list of IP addresses or CIDR subnets that are allowed to connect, e.g.:

   ```
   192.168.1.100, 10.0.0.0/24
   ```

   `127.0.0.1` is always the default. Invalid entries are rejected with an error dialog. Restart the RPC server after changing these settings.

### 2. Point the MCP server at the remote host

Pass the canonical `--rpc-host` option with the IP address or hostname of the
machine running FreeCAD (`--host` remains a deprecated alias):

```json
{
  "mcpServers": {
    "freecad": {
      "command": "uvx",
      "args": [
        "freecad-mcp",
        "--rpc-host", "192.168.1.100"
      ]
    }
  }
}
```

The `--host` value is validated on startup — it must be a valid IPv4/IPv6 address or hostname.

## Tools

> **Default modelling workflow.** For mechanical parts, build a real PartDesign feature
> history — `body_create` → `sketch_create`/`sketch_attach` → geometry → constraints →
> `get_sketch_diagnostics` → `pad_feature`/`pocket_feature` (pass `body_name`) →
> `recompute_document` → verify. The parts library and `create_object` primitives
> (`Part::Box`/`Cylinder`/`Cut`/`Fuse`) are for reference/non-parametric geometry, imported
> assets, temporary validation solids, or an explicitly requested primitive — not the
> default. See the `asset_creation_strategy` prompt.

### Documents & objects
* `create_document`, `list_documents`, `close_document`
* `get_objects`, `get_object`, `create_object`, `edit_object`
* `delete_object` — deletes without silently orphaning dependents (P6): `recursive=True` removes dependents first, `force=True` deletes only the object and reports the orphans left, otherwise it refuses and lists them.
* `execute_code`, `execute_code_async`, `recompute_document`, `undo`, `redo`, `reload_document`
* `get_recompute_log` — per-object recompute state (read-only); includes expression bindings when present.

### Parametric (Spreadsheet + expressions)
* `spreadsheet_create`, `spreadsheet_set_cells`, `spreadsheet_get_cells`, `spreadsheet_set_alias`, `spreadsheet_list_aliases`
* `set_expression`, `clear_expression`, `list_expressions` — bind props like `Constraints[i]` / `Length` to `<<Sheet>>.Alias`
* `body_create`, `body_set_tip`, `sketch_attach` — Body → Sketch on `XY_Plane` → Pad/Pocket recipe
* `sketch_edit_constraint` — edit dimensional constraints by stable `name` (preferred) or index
* `diagnose_parametric` — invalid objects, expression issues, sketch constraint summaries
* `sketch_constrain_distance` / `sketch_constrain_radius` / `sketch_add_constraint` accept optional `name` for stable identity after trim/fillet

### Sketching
* `sketch_create`, `sketch_add_geometry`, `sketch_add_constraint`
* `sketch_add_line`, `sketch_add_circle`, `sketch_add_arc`, `sketch_add_rectangle`
* `sketch_add_polyline`, `sketch_add_bspline`, `sketch_add_bspline_through_points`, `sketch_add_bezier`, `sketch_add_ellipse`, `sketch_add_arc_of_ellipse`, `sketch_add_slot`, `sketch_add_regular_polygon`, `sketch_add_parametric_curve`, `sketch_import_points`, `sketch_toggle_construction`
* `sketch_trim`, `sketch_extend`, `sketch_split`, `sketch_fillet`, `sketch_offset`, `sketch_symmetry`
* `sketch_constrain_*` — coincident, horizontal, vertical, distance, radius, equal, parallel, perpendicular, tangent.
* `get_sketch_geometry`, `get_sketch_diagnostics`

### PartDesign features
* `pad_feature`, `pocket_feature`, `revolve_feature`, `loft_feature`, `sweep_feature`, `helical_sweep_feature`
* `fillet_feature`, `chamfer_feature`
* `linear_pattern_feature`, `polar_pattern_feature`, `mirror_feature`
* `create_spur_gear`
* Pad/pocket/loft/sweep append a silent-build assertion (I2) so a wrong-direction or misplaced build surfaces as a clear failure instead of being marked "Up-to-date".

### Booleans
* `boolean_union`, `boolean_difference`, `boolean_intersection`

### Gears
* `create_involute_gear`, `create_helical_gear`, `compute_gear_geometry`, `check_gear_pair`

### Measurement & transforms
* `measure_distance`, `measure_angle`, `measure_area`, `measure_volume`
* `bounding_box`, `center_of_mass`, `validate_geometry`
* `translate`, `rotate`, `scale`

### IO
* `export_step`, `import_step`, `export_stl`, `export_brep`, `import_brep`, `set_color`

### Assembly
* `create_assembly`, `create_assembly_joint`, `create_assembly_grounded_joint`, `solve_assembly`
* `build_path_wire`, `sweep_pipe`
* `create_part_container`, `create_subshape_binder`, `create_datum_plane`, `move_object`
* `get_document_tree`, `sketch_add_external_projection`
* `create_assembly_joint` warns when a referenced component's body has cross-body datums attached (M4 / P5 guardrail).

### FEM Analysis
* `run_fem_analysis` — runs the CalculiX solver on an existing `Fem::FemAnalysis` and returns summary results (max von Mises stress, max displacement, node count, working directory). Auto-creates a `SolverCcxTools` if the analysis has none. See [`examples/cantilever_fem.py`](examples/cantilever_fem.py) for an end-to-end usage example.

### Diagnostics (read-only guards for the silent FreeCAD behaviours in `doc/mcp-feedback-status.md`)
* `check_rpc_sync` — round-trip a unique nonce through the GUI queue. Run it after an `execute_code` timeout or before trusting follow-up model checks; a timeout or nonce mismatch means work should stop until the RPC queue is healthy.
* `preview_attachment` — inspect a datum's attachment and the cross-body placement-drop risk (P1).
* `find_faces`, `find_edges` — locate sub-shapes by geometry (type / normal / centre / radius), removing face/edge-index fragility.
* `face_normal`, `edge_axis` — global normal/axis of a single sub-shape, avoiding the Direction-vs-Axis trap (P8).
* `placement_audit` — per Body/Part placement + `getGlobalPlacement()` + cross-body datums referencing it (M3).
* `relink_references` — re-point every reference from one object to another, making rebuilds non-destructive (M5).
* `capture_state`, `geometric_diff` — structured geometric diff as a text-only fallback when a viewable image can't be returned (I10 / P10).
* Every mutating tool appends a compact recompute log (I3) so orphaned/Invalid objects surface immediately.

### Snapshot / restore
* `snapshot` — save the current document into a ring buffer of the last 5 states.
* `restore` — restore a snapshot in place (latest, or by id). A bad step is one call to undo (I7 / P12).

### Views & parts library
* `get_view` — returns an `ImageContent` screenshot when available; otherwise a compact geometric state of the focus object (P10 / I10 fallback).
* `insert_part_from_library`, `get_parts_list`

## Git sidecar integration (optional)

When `generate_git_sidecar_after_save` is `true` in `freecad_mcp_settings.json`, the MCP add-on invokes the standalone `freecad-git` tool after a successful `.FCStd` save. Sidecar generation is opt-in, non-fatal to the save, and does not duplicate serialization logic.

```json
{
  "generate_git_sidecar_after_save": true
}
```

Requires `freecad-git` to be installed (`pip install -e tools/freecad_git` from the parent FreeCAD repository).

## Testing (Docker only)

Run the suite via Docker Compose from this directory — do not rely on host `pytest` for sign-off (e2e needs FreeCADCmd):

```bash
docker compose run --rm unit   # mock-based ops / template generation
docker compose run --rm e2e    # live FreeCADCmd parametric + regression tests
docker compose run --rm core   # FreeCAD core C++ repro markers
```

## Contributors

<a href="https://github.com/neka-nat/freecad-mcp/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=neka-nat/freecad-mcp" />
</a>

Made with [contrib.rocks](https://contrib.rocks).
