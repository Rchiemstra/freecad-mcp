"""Stable worker lifecycle error codes."""

from __future__ import annotations

from typing import Any

_WORKER_LIFECYCLE_CODES = {
    "worker_cancelled": "WORKER_CANCELLED",
    "worker_timeout": "WORKER_TIMEOUT_DURING_EXECUTION",
    "worker_execution_error": "WORKER_TASK_FAILED",
    "worker_crash": "WORKER_TASK_FAILED",
}


def build_worker_error(error_code: str, error: str, **execution: Any) -> dict[str, Any]:
    stable_code = _WORKER_LIFECYCLE_CODES.get(error_code, error_code)
    return {
        "success": False,
        "is_error": True,
        "error_code": stable_code,
        **(
            {"legacy_error_code": error_code}
            if stable_code != error_code
            else {}
        ),
        "error": error,
        "execution": {
            "mode": "worker",
            "stage": (
                "cancelled"
                if stable_code == "WORKER_CANCELLED"
                else "timed_out"
                if stable_code.startswith("WORKER_TIMEOUT_")
                else "failed"
            ),
            **execution,
        },
    }
