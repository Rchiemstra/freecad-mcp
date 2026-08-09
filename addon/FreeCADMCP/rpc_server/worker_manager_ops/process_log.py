"""Drain subprocess stdout while retaining at most the protocol byte cap."""

from __future__ import annotations

import contextlib
import subprocess

from ..worker_protocol_ops.constants import MAX_STDOUT_BYTES


def drain_process_log(process: subprocess.Popen, target) -> None:
    stream = process.stdout
    if stream is None:
        return
    retained = 0
    try:
        while True:
            chunk = stream.read(64 * 1024)
            if not chunk:
                break
            remaining = max(0, MAX_STDOUT_BYTES - retained)
            if remaining:
                data = chunk[:remaining]
                target.write(data)
                retained += len(data)
    finally:
        with contextlib.suppress(Exception):
            stream.close()
