# Structured results

Every MCP response has readable text for legacy clients and authoritative
`structuredContent` using schema version 1:

```json
{
  "schema_version": 1,
  "status": "succeeded",
  "operation": "pad_feature",
  "message": "Pad created",
  "error": null,
  "error_code": null,
  "correlation": {
    "session_id": "...",
    "call_id": "...",
    "request_id": "...",
    "execution_id": "...",
    "worker_job_id": null,
    "document_session_uuid": "..."
  },
  "layers": {
    "transport_status": "succeeded",
    "tool_status": "succeeded",
    "backend_status": "succeeded",
    "transaction_status": "committed",
    "document_health_status": "healthy"
  },
  "data": {}
}
```

Normalized statuses are `succeeded`, `condition_false`, `warning`, `degraded`,
`rejected`, `failed`, `timed_out`, `cancelled`, and `unknown`. `condition_false`
is a successful observation and therefore has `isError=false`. Examples include
an idle/busy query, no collisions, or an unsynchronized queue whose response is
otherwise valid. A malformed response or nonce mismatch is a failure.

Backend error codes are passed through unchanged. Common cross-layer codes
include `GUI_TIMEOUT_BEFORE_EXECUTION`, `GUI_TIMEOUT_DURING_EXECUTION`,
`WORKER_TIMEOUT_DURING_EXECUTION`, `WORKER_CANCELLED`,
`TRANSACTION_ROLLBACK_FAILED`, and `INVALID_ARGUMENT`.

Protected rejection:

```json
{"status":"rejected","error_code":"UNSAFE_EXECUTE_SCOPE_REJECTED","data":{"success":false}}
```

Degraded document:

```json
{"status":"degraded","error_code":"DOCUMENT_HEALTH_DEGRADED","document_health":{"verdict":"degraded"}}
```

Screenshots remain MCP `ImageContent`; base64 bodies are never duplicated into
structured JSON.
