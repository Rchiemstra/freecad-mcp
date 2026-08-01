"""Thread-safe XML-RPC ServerProxy lane."""

from __future__ import annotations

import threading
import xmlrpc.client
from collections.abc import Callable
from typing import Any

from .timeout_transport import TimeoutTransport


class ProxyLane:
    """Thread-safe ServerProxy lane with independent connection state.

    General work and control/heartbeat work use different instances so a long
    modelling call cannot hold the transport lock needed by a lease renewal.
    """

    def __init__(
        self,
        uri: str,
        timeout: float,
        header_provider: Callable[[str, tuple[Any, ...]], tuple[tuple[str, str], ...]],
    ) -> None:
        self._header_provider = header_provider
        self._lock = threading.RLock()
        self.transport = TimeoutTransport(timeout=timeout)
        self._proxy = xmlrpc.client.ServerProxy(
            uri,
            allow_none=True,
            transport=self.transport,
        )

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        from .proxy_method import ProxyMethod

        return ProxyMethod(self, name)

    def call(
        self,
        method: str,
        *args: Any,
        extra_headers: tuple[tuple[str, str], ...] = (),
    ) -> Any:
        with self._lock:
            self.transport.extra_headers = list(
                self._header_provider(method, tuple(args))
            ) + list(extra_headers)
            try:
                target: Any = self._proxy
                for segment in method.split("."):
                    target = getattr(target, segment)
                return target(*args)
            finally:
                self.transport.extra_headers = []

    def close(self) -> None:
        with self._lock:
            self.transport.extra_headers = []
            self.transport.close()
