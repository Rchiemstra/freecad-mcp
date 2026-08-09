"""Detect whether a path resides on a network filesystem."""

from __future__ import annotations

import os
from pathlib import Path


def is_network_path(path: Path) -> bool:
    value = str(path)
    if value.startswith("\\\\") or value.startswith("//"):
        return True
    if os.name == "nt":
        return _is_windows_network_path(value)
    if os.path.isfile("/proc/self/mountinfo"):
        return _is_linux_network_path(value)
    return False


def _is_windows_network_path(value: str) -> bool:
    # UNC checks do not catch mapped network drives. Query the resolved
    # drive root without touching the target file; DRIVE_REMOTE is 4.
    try:
        import ctypes

        absolute = os.path.abspath(value)
        drive, _tail = os.path.splitdrive(absolute)
        if drive:
            root = drive + "\\"
            return int(ctypes.windll.kernel32.GetDriveTypeW(root)) == 4
    except (AttributeError, OSError, ValueError):
        # Detection uncertainty is handled by the caller's other
        # fail-closed filesystem/permission checks.
        pass
    return False


def _is_linux_network_path(value: str) -> bool:
    # Linux exposes the filesystem type after the " - " separator. Use
    # the longest matching mount point so a local parent mount cannot mask
    # an NFS/CIFS/SSHFS child mount.
    network_types = {
        "9p",
        "afs",
        "ceph",
        "cifs",
        "fuse.sshfs",
        "ncpfs",
        "nfs",
        "nfs4",
        "smb3",
    }
    try:
        target = os.path.realpath(os.path.abspath(value))
        matches: list[tuple[int, str]] = []
        with open("/proc/self/mountinfo", encoding="utf-8") as mounts:
            for line in mounts:
                left, separator, right = line.rstrip("\n").partition(" - ")
                if not separator:
                    continue
                fields = left.split()
                filesystem = right.split(maxsplit=1)[0]
                if len(fields) < 5:
                    continue
                mount_point = (
                    fields[4]
                    .replace("\\040", " ")
                    .replace("\\011", "\t")
                    .replace("\\134", "\\")
                )
                if target == mount_point or target.startswith(
                    mount_point.rstrip(os.sep) + os.sep
                ):
                    matches.append((len(mount_point), filesystem))
        if matches:
            return max(matches)[1].lower() in network_types
    except (OSError, ValueError):
        pass
    return False
