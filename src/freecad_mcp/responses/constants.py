from mcp.types import CallToolResult

from ..outcomes import OutcomeStatus

ToolResponse = CallToolResult

_PROTECTED_ENVELOPE_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "operation",
        "message",
        "error",
        "error_code",
        "correlation",
        "layers",
        "data",
        "execution",
        "transaction",
        "document_health",
        "mutation_scope",
    }
)
_ERROR_STATUSES = frozenset(
    {
        OutcomeStatus.DEGRADED.value,
        OutcomeStatus.REJECTED.value,
        OutcomeStatus.FAILED.value,
        OutcomeStatus.TIMED_OUT.value,
        OutcomeStatus.CANCELLED.value,
        OutcomeStatus.UNKNOWN.value,
    }
)
