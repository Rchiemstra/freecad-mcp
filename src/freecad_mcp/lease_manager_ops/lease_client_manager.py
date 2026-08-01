"""Thread-safe MCP-side lease-token owner and document alias index."""

from __future__ import annotations


class LeaseClientManager:
    """Thread-safe MCP-side lease-token owner and document alias index."""


from .lease_client_manager_bindings import bind_lease_client_manager  # noqa: E402

bind_lease_client_manager(LeaseClientManager)
