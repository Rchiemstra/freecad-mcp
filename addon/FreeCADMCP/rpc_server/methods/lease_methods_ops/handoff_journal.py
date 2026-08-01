"""Terminal journaling for LOCKED_ERROR handoff continuation."""

from ._common import _rpc_mod, logger


def journal_handoff_terminal(self, *, mcp_runtime_id, request_id, response):
    if _rpc_mod().rpc_request_replay_cache is None or not mcp_runtime_id or not request_id:
        return
    try:
        _rpc_mod().rpc_request_replay_cache.journal_completion(
            mcp_runtime_id, request_id, response
        )
    except Exception:
        logger.debug(
            "handoff continuation journal_completion failed", exc_info=True
        )
