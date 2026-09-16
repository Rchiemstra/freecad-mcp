"""Thin correlation bridge between experimental MCP Tasks and existing jobs."""

from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass
from typing import Any

HEAVY_TASK_TOOLS = frozenset(
    {
        "animate_placement",
        "cancel_worker_job",
        "common_volume_along_path",
        "encode_view_video",
        "execute_code",
        "export_brep",
        "export_step",
        "export_stl",
        "finalize_document_edit",
        "run_fem_analysis",
        "save_document",
        "save_document_as",
        "save_document_copy",
        "save_view_sequence",
        "validate_geometry",
    }
)


@dataclass
class TaskLink:
    task_id: str
    tool_name: str
    request_id: str = ""
    worker_job_id: str = ""
    status: str = "working"
    created_monotonic: float = 0.0
    updated_monotonic: float = 0.0

    def public(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("created_monotonic", None)
        value.pop("updated_monotonic", None)
        return value


_LINKS: dict[str, TaskLink] = {}
_LOCK = threading.RLock()


def register(task_id: str, tool_name: str) -> TaskLink:
    now = time.monotonic()
    with _LOCK:
        link = TaskLink(
            task_id=str(task_id),
            tool_name=str(tool_name),
            created_monotonic=now,
            updated_monotonic=now,
        )
        _LINKS[link.task_id] = link
        return link


def link_runtime(
    task_id: str,
    *,
    request_id: str | None = None,
    worker_job_id: str | None = None,
) -> TaskLink | None:
    if not task_id:
        return None
    with _LOCK:
        link = _LINKS.get(str(task_id))
        if link is None:
            return None
        if request_id:
            link.request_id = str(request_id)
        if worker_job_id:
            link.worker_job_id = str(worker_job_id)
        link.updated_monotonic = time.monotonic()
        return link


def finish(task_id: str, status: str) -> TaskLink | None:
    with _LOCK:
        link = _LINKS.get(str(task_id))
        if link is not None:
            link.status = str(status)
            link.updated_monotonic = time.monotonic()
        return link


def get(task_id: str) -> dict[str, Any] | None:
    with _LOCK:
        link = _LINKS.get(str(task_id))
        return link.public() if link is not None else None


__all__ = [
    "HEAVY_TASK_TOOLS",
    "TaskLink",
    "finish",
    "get",
    "link_runtime",
    "register",
]
