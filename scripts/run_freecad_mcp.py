#!/usr/bin/env python3
"""Launch the FreeCAD MCP server.

Default (``FREECAD_MCP_DEBUG`` unset or ``0``): run ``freecad_mcp.server.main``
in-process — no wrapper subprocess, no debug log.

Instrumented mode (``FREECAD_MCP_DEBUG=1``): spawn the server in a child process
with redacted/rotated JSON-RPC tracing. The child tree is terminated on exit.
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_inprocess(extra_argv: list[str]) -> int:
    from freecad_mcp.server import main

    sys.argv = ["freecad-mcp", *extra_argv]
    main()
    return 0


def _run_instrumented(extra_argv: list[str]) -> int:
    root = _repo_root()
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

    from freecad_mcp.debug_log import debug_enabled, log_event
    from freecad_mcp.process_tree import WindowsJobObject, kill_process_tree

    if not debug_enabled():
        return _run_inprocess(extra_argv)

    env = os.environ.copy()
    env.setdefault("FREECAD_MCP_DEBUG", "1")

    cmd = [sys.executable, "-m", "freecad_mcp.server", *extra_argv]
    log_event("wrapper", method="start", payload={"cmd": cmd, "pid": os.getpid()})

    child = subprocess.Popen(
        cmd,
        env=env,
        cwd=str(root),
    )
    job: WindowsJobObject | None = None
    try:
        job = WindowsJobObject()
        job.assign(child.pid)
    except Exception:
        job = None

    def _forward(signum: int, _frame: object) -> None:
        try:
            if sys.platform == "win32":
                child.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                child.send_signal(signum)
        except Exception:
            kill_process_tree(child.pid)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _forward)
        except Exception:
            pass

    started = time.time()
    rc = 1
    try:
        rc = child.wait()
    finally:
        duration_ms = (time.time() - started) * 1000
        log_event(
            "wrapper",
            method="exit",
            status="ok" if rc == 0 else "error",
            duration_ms=duration_ms,
            payload={"child_pid": child.pid, "returncode": rc},
        )
        kill_process_tree(child.pid)
        if job is not None:
            job.close()

    return rc


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the FreeCAD MCP server")
    parser.add_argument("--only-text-feedback", action="store_true")
    parser.add_argument("--host", default="localhost")
    args, unknown = parser.parse_known_args()

    extra: list[str] = []
    if args.only_text_feedback:
        extra.append("--only-text-feedback")
    if args.host:
        extra.extend(["--host", args.host])
    extra.extend(unknown)

    if os.environ.get("FREECAD_MCP_DEBUG", "0") == "1":
        return _run_instrumented(extra)
    return _run_inprocess(extra)


if __name__ == "__main__":
    raise SystemExit(main())
