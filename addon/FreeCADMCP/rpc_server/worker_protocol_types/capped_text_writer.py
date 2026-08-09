"""Bounded stdout capture for isolated worker processes."""

from ..worker_protocol_ops.constants import MAX_STDOUT_BYTES


class CappedTextWriter:
    """Capture text without ever retaining more than the configured byte cap."""

    def __init__(self, limit: int = MAX_STDOUT_BYTES):
        self.limit = limit
        self._data = bytearray()
        self.truncated = False

    def write(self, value: str) -> int:
        encoded = str(value).encode("utf-8", errors="replace")
        remaining = max(0, self.limit - len(self._data))
        if remaining:
            self._data.extend(encoded[:remaining])
        if len(encoded) > remaining:
            self.truncated = True
        return len(value)

    def flush(self) -> None:
        return None

    def getvalue(self) -> str:
        return bytes(self._data).decode("utf-8", errors="replace")
