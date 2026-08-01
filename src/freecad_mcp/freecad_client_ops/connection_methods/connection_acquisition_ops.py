"""FreeCADConnection method implementations."""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from typing import Any

from .connection_acquisition_helpers import poll_locked_error_handoff

logger = logging.getLogger("FreeCADMCPserver")



def _recover_acquisition_after_transport_loss(
        conn,
        method: str,
        request_id: str,
        *,
        params: Mapping[str, Any] | None = None,
        poll_attempts: int = 8,
        poll_interval_s: float = 0.25,
    ) -> dict[str, Any] | None:
        """Status/claim recovery after the acquisition XML-RPC response is lost.

        Returns an invoke_v2-shaped success envelope when the credential can be
        reclaimed; otherwise ``None`` so the caller re-raises with request_id.
        """

        del params  # reserved for future selector-aware status filtering
        target = str(request_id or "")
        if not target:
            return None
        deadline = time.monotonic() + max(1.0, poll_attempts * poll_interval_s)
        last_status: dict[str, Any] | None = None
        while time.monotonic() <= deadline:
            try:
                last_status = conn.get_request_status(target)
            except Exception:
                last_status = None
            if isinstance(last_status, Mapping) and last_status.get("success"):
                state = str(last_status.get("state") or "")
                claimable = bool(
                    last_status.get("result_claimable")
                    or (
                        isinstance(last_status.get("acquisition_claim"), Mapping)
                        and last_status["acquisition_claim"].get("claimable")
                    )
                )
                if claimable or state in {"completed", "completed_after_cancel_request"}:
                    claimed = conn.claim_acquisition_result(target)
                    if (
                        isinstance(claimed, Mapping)
                        and claimed.get("success")
                        and isinstance(claimed.get("credential"), Mapping)
                        and claimed["credential"].get("token")
                    ):
                        # Ack only after the tool path custodied the token.
                        return {
                            "ok": True,
                            "request_id": target,
                            "result": claimed,
                            "recovered_after_transport_loss": True,
                        }
                if state in {
                    "failed",
                    "cancelled",
                    "expired",
                    "unknown",
                }:
                    return {
                        "ok": False,
                        "request_id": target,
                        "result": {
                            "success": False,
                            "error_code": "ACQUISITION_RECOVERY_FAILED",
                            "error": (
                                "Acquisition transport was lost and the request "
                                f"finished as {state}"
                            ),
                            "request_id": target,
                            "status": last_status,
                        },
                    }
                if state not in {
                    "queued",
                    "running",
                    "running_after_timeout",
                    "cancel_requested",
                }:
                    break
            time.sleep(poll_interval_s)
        if last_status is not None:
            return {
                "ok": False,
                "request_id": target,
                "result": {
                    "success": False,
                    "error_code": "ACQUISITION_RECOVERY_PENDING",
                    "error": (
                        "Acquisition transport was lost; poll get_request_status "
                        "and claim_acquisition_result with the request_id"
                    ),
                    "request_id": target,
                    "status": last_status,
                },
            }
        return None


def _resolve_locked_error_handoff_pending(
        conn,
        result: Mapping[str, Any],
        *,
        poll_interval_s: float = 0.5,
        max_wait_s: float | None = None,
    ) -> dict[str, Any]:
        """Optional helper: poll control-lane status/claim after handoff detect.

        Public ``adopt_dirty_document`` returns pending immediately; callers
        should use ``get_request_status`` / ``claim_acquisition_result``. This
        await is retained for tests and internal tooling only. It terminates on
        disconnect, permanent auth failures, terminal status, or ``max_wait_s``.
        """

        if not isinstance(result, Mapping):
            return dict(result) if result else {"success": False}
        if result.get("error_code") != "LOCKED_ERROR_HANDOFF_PENDING":
            return dict(result)
        target = str(result.get("request_id") or "")
        if not target:
            return dict(result)
        deadline = (
            None if max_wait_s is None else time.monotonic() + float(max_wait_s)
        )
        return poll_locked_error_handoff(
            conn,
            target,
            poll_interval_s=poll_interval_s,
            deadline=deadline,
        )
