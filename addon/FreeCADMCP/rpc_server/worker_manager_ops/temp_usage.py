"""Managed temporary root usage and stale workspace cleanup."""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path


def temp_usage(temp_root: Path) -> int:
    """Measure managed files without following links outside the temp root."""
    total = 0
    pending = [temp_root]
    while pending:
        directory = pending.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    pending.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    total += entry.stat(follow_symlinks=False).st_size
            except OSError:
                pass
    return total


def sweep_stale_workspaces(temp_root: Path, artifact_root: Path) -> None:
    cutoff = time.time() - 24 * 60 * 60
    for child in temp_root.glob("mcp_worker_*"):
        try:
            if child.stat().st_mtime < cutoff:
                shutil.rmtree(child, ignore_errors=True)
        except OSError:
            pass
    sweep_stale_artifacts(artifact_root)


def sweep_stale_artifacts(artifact_root: Path) -> None:
    artifact_cutoff = time.time() - 60 * 60
    if artifact_root.exists():
        for child in artifact_root.iterdir():
            try:
                if child.stat().st_mtime < artifact_cutoff:
                    shutil.rmtree(child, ignore_errors=True)
            except OSError:
                pass
