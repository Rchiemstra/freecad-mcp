# Runtime and build identity

Install both halves from one `Rchiemstra/freecad-mcp` checkout:

```bash
git clone https://github.com/Rchiemstra/freecad-mcp.git
cd freecad-mcp
python -m pip install -e .
```

Copy `addon/FreeCADMCP` from that checkout into the active FreeCAD profile.
The original upstream is `neka-nat/freecad-mcp`; it is not the checkout used by
the commands above.

`freecad_mcp.build_info` is the package authority for `version`, `build_id`,
Git commit/dirty state, build timestamp, RPC protocol, and telemetry schema.
It never requires `.git` at runtime. Without injected metadata the deterministic
build ID is `freecad-mcp-<version>+unknown`.

CI can set `FREECAD_MCP_BUILD_ID`, `FREECAD_MCP_GIT_COMMIT`,
`FREECAD_MCP_GIT_DIRTY`, and `FREECAD_MCP_BUILD_TIMESTAMP`, or run:

```bash
python scripts/generate_build_metadata.py \
  --version 0.2.0 --git-commit "$GIT_SHA"
```

That creates matching package and addon metadata. The addon also accepts the
same environment variables for controlled deployments.

Call `get_runtime_info` to inspect the connected MCP process, addon runtime,
FreeCAD PID/version/revision, protocol features, and isolated profile
fingerprint. Build/version differences are warnings when protocol and required
features remain compatible. Protocol or required-feature mismatches fail
authentication; exact isolated profile/PID verification remains fail closed.
Tokens, proofs, and lease credentials are not returned.
