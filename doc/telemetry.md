# Telemetry

FreeCAD MCP writes versioned JSONL events with microsecond UTC timestamps,
monotonic nanoseconds, per-session sequence numbers, status, duration, error
code, and correlation fields. Sources cover MCP, authentication, routing, RPC,
GUI dispatch, workers, transactions, document health, cancellation, recovery,
and execute-code adoption.

One MCP writer owns one file per process/session:

```text
debug_logs/mcp_debug_2026-07-27_<pid>_<session>.jsonl
```

The addon writes its own `addon_debug_...jsonl` because it is independently
installable. Files are flushed per line; both writers rotate by configured size
with bounded backups.
Set `FREECAD_MCP_TELEMETRY=0` to disable, `FREECAD_MCP_DEBUG_LOG_DIR` to select
a directory, or `FREECAD_MCP_TELEMETRY_FILE` for a controlled MCP test path.
Size and backup bounds use `FREECAD_MCP_TELEMETRY_MAX_BYTES` and
`FREECAD_MCP_TELEMETRY_BACKUPS`.

Credential-shaped fields are replaced, exact discovered secrets are scrubbed
from other strings, source code and image/base64 bodies become SHA-256/byte
summaries, and oversized payloads become bounded truncation records. Normal
telemetry never contains raw Python or credential values.

Merge and analyze independent files with:

```bash
python scripts/merge_mcp_telemetry.py debug_logs/*.jsonl -o merged.jsonl
python scripts/analyze_mcp_telemetry.py merged.jsonl -o telemetry-report.json
```

The schema is `src/freecad_mcp/telemetry/schema.json`. The legacy parser is
migration-only and KPI tooling consumes schema-v1 JSONL.
