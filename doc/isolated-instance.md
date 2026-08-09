# Isolated FreeCAD MCP instance

The isolated workflow uses a private FreeCAD profile and a dedicated RPC
endpoint. It does not alter, connect to, stop, or reuse the existing `freecad`
MCP configuration or the default RPC listener on port 9875.

## Setup and launch

From `tools/mcp/freecad-mcp`:

```powershell
python scripts/setup_isolated_profile.py
python scripts/setup_cursor_mcp_isolated.py
python scripts/start_freecad_isolated.py
```

`setup_isolated_profile.py` creates `<FreeCAD-repo>/.freecad-mcp-isolated` with:

- a junction/symlink to the addon under `Mod/FreeCADMCP`;
- `freecad_mcp_settings.json` using `rpc_bind_host=127.0.0.1`, port 9876,
  `document_lease_mode=enforce`, network sidecars off, persisted task summaries
  off, and unsafe live code off;
- a persistent random `profile_instance_id`;
- a raw 32-byte `freecad_mcp_auth.secret` protected for the current owner;
- `instance-manifest.json`, which contains the secret file path but never its
  contents.

Rerunning setup preserves the profile identity and secret. `--instance-id` is
available only as a first-setup compatibility override; a later mismatching
value is rejected. `--port` changes the isolated endpoint but does not derive
or replace the profile identity.

`setup_cursor_mcp_isolated.py` reads this manifest and atomically adds or
updates only `mcpServers.freecad-isolated`. It explicitly verifies that an
existing `mcpServers.freecad` value is unchanged. The generated command passes
`--rpc-host`, `--rpc-port`, `--instance-id`, `--instance-manifest`, and
`--auth-file`; environment values contain paths and IDs, never secret bytes.

## Manifest

Manifest schema 1 includes:

```json
{
  "schema_version": 1,
  "rpc_host": "127.0.0.1",
  "rpc_port": 9876,
  "profile_instance_id": "<random uuid>",
  "profile_path": ".../.freecad-mcp-isolated",
  "auth_secret_file": ".../freecad_mcp_auth.secret",
  "expected_freecad_pid": null,
  "expected_freecad_process_started_at": null,
  "expected_addon_runtime_id": null,
  "expected_boot_id": null,
  "expected_protocol_version": null,
  "expected_protocol_features": null,
  "expected_addon_version": null,
  "expected_addon_build_id": null,
  "expected_freecad_version": null,
  "expected_freecad_revision": null,
  "expected_profile_path_fingerprint": null,
  "created_at": "RFC3339Z"
}
```

The launcher accepts only the exact schema fields above, absolute profile and
secret paths, and an explicit loopback IP endpoint. It reserves the endpoint
with an exclusive local bind while preparing the child, without connecting or
sending anything to an existing listener. The reservation is released
immediately before FreeCAD is spawned; this is the narrowest bind handoff
possible until the addon can inherit a pre-bound socket.

After launching FreeCAD, `get_instance_info` is only an unauthenticated
discovery hint. The launcher sends a nonce-bearing `handshake_v2` request signed
with the profile secret and accepts readiness only after verifying the server's
HMAC response. The authenticated manifest must prove the launched PID, profile
ID, process start, runtime UUID, profile-path fingerprint, actual endpoint,
protocol version and exact features, addon version/build, and FreeCAD
version/revision. Only those authenticated facts are recorded for MCP handshake
pinning; no candidate fact is written before verification. A mismatch fails
without adopting or stopping the answering process. On session refresh, the MCP
reloads this same atomically replaced manifest and accepts a new runtime only
when profile identity/path, endpoint, authentication path, schema, and creation
identity remain unchanged and the new full identity completes the HMAC proof.

The wrapper accepts canonical `--rpc-host`/`--rpc-port`; `--host`/`--port`
remain aliases. Debug mode invokes `freecad_mcp.server.main()` explicitly
because the module is a project entry point, not a `python -m` executable.

## Remote use

The isolated manifest is deliberately loopback-only. HMAC authenticates an MCP
runtime but does not encrypt XML-RPC traffic. For remote use, keep the manifest
endpoint local and connect an SSH tunnel or TLS proxy to that loopback endpoint;
do not replace `rpc_host` with a LAN address. See
[lease security](lease-security.md).
