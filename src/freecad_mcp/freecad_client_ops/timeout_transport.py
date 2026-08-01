"""_TimeoutTransport — extracted from lease_manager."""

from __future__ import annotations

import xmlrpc.client


class TimeoutTransport(xmlrpc.client.Transport):
    """XML-RPC transport with a configurable socket timeout and MCP headers.

    The default Transport has no timeout, so a frozen FreeCAD GUI thread
    causes the MCP client to hang indefinitely (observed: 4+ minute waits).

    ``extra_headers`` are installed only while a serialized proxy lane owns the
    transport. This keeps the underlying HTTP connection reusable without
    allowing concurrent requests to overwrite one another's authentication.
    """

    def __init__(self, timeout: float = 30, **kwargs):
        super().__init__(**kwargs)
        self._timeout = timeout
        # Access is serialized by _ProxyLane.
        self.extra_headers: list[tuple[str, str]] = []

    def make_connection(self, host):
        conn = super().make_connection(host)
        conn.timeout = self._timeout
        return conn

    def send_headers(self, connection, headers):
        if self.extra_headers:
            # Prefer our identity headers; append after the stock ones
            headers = list(headers) + list(self.extra_headers)
        return super().send_headers(connection, headers)
