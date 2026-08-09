"""Bounded process-tree termination for isolated FreeCADCmd workers."""

from __future__ import annotations

# §3.3 compatibility shims — moved symbols keep their legacy import path.
from .process_control_ops.terminate import (
    CREATE_NEW_PROCESS_GROUP,
    CREATE_NO_WINDOW,
    popen_platform_options,
    terminate_process_tree,
)
from .process_control_types.windows_job_object import WindowsJobObject

__all__ = [
    "CREATE_NEW_PROCESS_GROUP",
    "CREATE_NO_WINDOW",
    "WindowsJobObject",
    "popen_platform_options",
    "terminate_process_tree",
]
