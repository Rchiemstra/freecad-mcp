# Advanced setup and testing

[Back to the README](../README.md#advanced) · [All tools](tools.md).

## Leases and isolated profiles

A write lease gives one cooperative MCP runtime ownership of one document.
The runtime retains its lease credential in memory, renews it and attaches it to
scoped mutations. Use `acquire_document_lock` before editing in `enforce` mode
and `finalize_document_edit` to validate, save and release. A failed save or
mutation can retain the lease for retry or recovery; inspect its reported state.

New ordinary profiles default to `document_lease_mode=observe`. `enforce`
requires a UUID profile identity, an owner-only authentication secret, protocol
v2 and exact credentials. `off` preserves legacy compatibility; recognised active
foreign v2 sidecars can still block writes. See the
[lease lifecycle](document-leases.md) for migration rules and GUI behaviour.

Leases prevent accidental conflicts between cooperative MCP writers. They do not
sandbox Python, macros or other processes running as the same OS user.
See [the security boundary](lease-security.md).

For development beside an existing session, the repository provides a separate
manifest-driven profile and Cursor entry:

```powershell
python scripts/setup_isolated_profile.py
python scripts/setup_cursor_mcp_isolated.py
python scripts/start_freecad_isolated.py
```

These scripts maintain the `freecad-isolated` entry without changing the existing
`freecad` entry. The private profile uses port 9876, its own identity and secret,
and lease enforcement. The launcher verifies the launched process through an
authenticated handshake. See [isolated instance setup](isolated-instance.md),
[client scenarios](lease-client-scenarios.md), [sidecar schema](document-lease-sidecar-v2.md)
and [crash recovery](lease-recovery.md).

## Remote connections and headless checks

The addon defaults to loopback RPC on `127.0.0.1:9875`. HMAC authenticates
protocol-v2 messages but does not encrypt session or lease credentials.
Keep FreeCAD bound to loopback and reach it through an SSH tunnel or TLS proxy.
An `enforce` profile rejects a plain non-loopback bind by default.

Point the MCP command at the local tunnel endpoint with `--rpc-host` and
`--rpc-port`. For the default port, append these arguments after `freecad-mcp`
in the [client configuration](../README.md#3-connect-your-assistant):

```json
["--rpc-host", "127.0.0.1", "--rpc-port", "9875"]
```

`--host` and `--port` remain deprecated aliases. An isolated instance manifest
pins its endpoint and authenticated identity; follow its
[remote-use rules](isolated-instance.md#remote-use).

For an `off` or `observe` profile on a trusted isolated network, the legacy
direct connection workflow is:

1. In the FreeCAD MCP toolbar, enable **Remote Connections**. It selects
   `0.0.0.0` when the configured bind address is loopback.
2. Use **Configure Allowed IPs** to set a comma-separated list of addresses or
   CIDR subnets, such as `192.168.1.100, 10.0.0.0/24`. The default is `127.0.0.1`.
3. Restart the RPC server, then pass `--rpc-host` with the FreeCAD host address
   to the MCP command.

The addon rejects invalid allowlist entries. The CLI validates hostnames and
IPv4/IPv6 addresses. See [lease security](lease-security.md) for transport policy.

For expensive read-only geometry checks, call `get_worker_status` first. Use
`execute_code` with an explicit document, `read_only=true`,
`execution_mode="worker"` and `timeout_seconds`. The worker opens a snapshot
in a separate FreeCADCmd process. It can change that disposable copy for analysis;
it does not change the live GUI documents. `common_volume_along_path` uses this
read-only worker for sampled overlap checks.

This needs an available compatible FreeCADCmd executable. GUI screenshots still
need a FreeCAD viewport. A headless worker is an analysis path, not a replacement
for every GUI tool. See [geometry-loop routing](gui-geometry-loop-guard.md).

After a timeout, use `get_request_status` and `check_rpc_sync` to resolve request
state before continuing. Cancellation is cooperative for live requests; worker
jobs can be terminated through `cancel_worker_job`. See
[request lifecycle](request-lifecycle.md) and [runtime identity](runtime-identity.md).

## Git sidecar

Set this in the addon's `freecad_mcp_settings.json` to request a sidecar after a
successful eligible `.FCStd` save:

```json
{
  "generate_git_sidecar_after_save": true
}
```

The [save observer](../addon/FreeCADMCP/git_sidecar.py) invokes the separately
installed `freecad_git.cli export` command. Sidecar generation is opt-in, and a
sidecar failure does not fail the document save. The adapter skips snapshots,
recovery files and backup targets.

The `freecad-git` package must be available to the Python environment the addon
uses. In the parent FreeCAD repository, its editable install command is
`pip install -e tools/freecad_git`; that package is not bundled in this checkout.
The [unit tests](../tests/git/test_git_sidecar.py) and
[integration test](../tests/git/test_git_sidecar_integration.py) cover the adapter.

## Testing

Run the Docker Compose lanes from this repository directory:

```bash
docker compose run --rm unit
docker compose run --rm e2e
docker compose run --rm core
docker compose run --rm benchmark
```

The [Compose file](../docker-compose.yml) defines these services. Unit tests use
mocks; e2e and core tests need FreeCAD. The
[stock compatibility image](../Dockerfile) skips branch-native mutation tests;
passing it does not qualify the native APIs required by typed modelling.
Use the [native qualification workflow](body-create-reference.md#repeating-qualification)
with a branch-built FreeCAD runtime for that evidence. Host-only mock tests do
not establish live FreeCAD behaviour.

The benchmark writes `benchmark-results.json` and `benchmark-report.md`.
See [benchmarking](benchmarking.md) for metrics, output locations and quality gates.
Telemetry defaults to per-process/session JSONL files under `debug_logs/`;
`FREECAD_MCP_DEBUG_LOG_DIR` selects another directory. See [telemetry](telemetry.md).
