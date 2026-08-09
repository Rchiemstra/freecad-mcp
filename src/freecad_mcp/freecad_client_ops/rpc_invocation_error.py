"""RpcInvocationError — extracted from lease_manager."""

from __future__ import annotations


class RpcInvocationError(RuntimeError):
    """Credential-safe transport failure for an authenticated invocation."""

    def __init__(
        self,
        method: str,
        cause: BaseException,
        *,
        request_id: str | None = None,
        protocol_code: str | None = None,
        lane: str | None = None,
    ) -> None:
        self.method = method
        self.request_id = str(request_id or "") or None
        self.protocol_code = str(protocol_code or "") or None
        self.lane = str(lane or "") or None
        self.code = self.protocol_code or type(cause).__name__.upper()
        self.cause = cause
        detail = f"Authenticated RPC {method!r} failed ({type(cause).__name__})"
        if self.protocol_code:
            detail = f"{detail}; protocol_code={self.protocol_code}"
        if self.lane:
            detail = f"{detail}; lane={self.lane}"
        if self.request_id:
            detail = f"{detail}; request_id={self.request_id}"
        super().__init__(detail)
