from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from typing import Any

from ..rpc_session import RpcAuthenticationContext


def _generated_execute_signature(
    *,
    session_token: str,
    request_id: str,
    code: str,
    options: Mapping[str, Any],
) -> str:
    """Authenticate the internal generated-code capability marker.

    The public MCP ``execute_code`` signature cannot supply this value.  It is
    added at the transport boundary and is bound to the immutable v2 request,
    exact code, operation id, and declared document scope.
    """

    affected = options.get("affected_documents") or ()
    payload = {
        "request_id": request_id,
        "operation_id": str(options.get("operation_id") or ""),
        "code_sha256": hashlib.sha256(code.encode("utf-8")).hexdigest(),
        "document": str(options.get("document") or ""),
        "affected_documents": sorted({str(item) for item in affected}),
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hmac.new(session_token.encode("utf-8"), canonical, hashlib.sha256)
    return f"hmac-sha256:{digest.hexdigest()}"


def _sign_generated_execute_params(
    method: str,
    params: Mapping[str, Any] | None,
    context: RpcAuthenticationContext,
) -> Mapping[str, Any] | None:
    if method != "execute_code" or not isinstance(params, Mapping):
        return params
    raw_options = params.get("options")
    code = params.get("code")
    if (
        not isinstance(raw_options, Mapping)
        or not raw_options.get("generated_operation")
        or not isinstance(code, str)
    ):
        return params
    options = dict(raw_options)
    options["operation_signature"] = _generated_execute_signature(
        session_token=context.session_token,
        request_id=context.request_id,
        code=code,
        options=options,
    )
    signed = dict(params)
    signed["options"] = options
    return signed


