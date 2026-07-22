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
    root = _repo_root()
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

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

    # freecad_mcp.server exposes a project entry point but intentionally has no
    # ``python -m`` guard. Invoke main explicitly so debug mode actually starts
    # the server instead of importing the module and exiting successfully.
    cmd = _instrumented_command(extra_argv)
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


def _instrumented_command(extra_argv: list[str]) -> list[str]:
    return [
        sys.executable,
        "-c",
        "from freecad_mcp.server import main; main()",
        *extra_argv,
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the FreeCAD MCP server")
    parser.add_argument("--only-text-feedback", action="store_true")
    parser.add_argument(
        "--rpc-host",
        "--host",
        dest="rpc_host",
        default=None,
        help=(
            "FreeCAD RPC host (default: FREECAD_MCP_RPC_HOST or 127.0.0.1). "
            "--host is retained as a compatibility alias."
        ),
    )
    parser.add_argument(
        "--rpc-port",
        "--port",
        dest="rpc_port",
        type=int,
        default=None,
        help=(
            "FreeCAD RPC port (default: FREECAD_MCP_PORT or 9875). "
            "--port is retained as a compatibility alias."
        ),
    )
    parser.add_argument("--instance-id", default=None)
    parser.add_argument("--instance-manifest", default=None)
    parser.add_argument("--auth-file", default=None)
    args, unknown = parser.parse_known_args()

    extra: list[str] = []
    if args.only_text_feedback:
        extra.append("--only-text-feedback")
    rpc_host = args.rpc_host or os.environ.get("FREECAD_MCP_RPC_HOST") or "127.0.0.1"
    extra.extend(["--rpc-host", rpc_host])
    if args.rpc_port is not None:
        extra.extend(["--rpc-port", str(args.rpc_port)])
    elif os.environ.get("FREECAD_MCP_PORT"):
        extra.extend(["--rpc-port", os.environ["FREECAD_MCP_PORT"]])
    instance_id = args.instance_id or os.environ.get("FREECAD_MCP_INSTANCE_ID")
    instance_manifest = args.instance_manifest or os.environ.get(
        "FREECAD_MCP_INSTANCE_MANIFEST"
    )
    auth_file = args.auth_file or os.environ.get("FREECAD_MCP_AUTH_FILE")
    if instance_id:
        extra.extend(["--instance-id", instance_id])
    if instance_manifest:
        extra.extend(["--instance-manifest", instance_manifest])
    if auth_file:
        extra.extend(["--auth-file", auth_file])
    extra.extend(unknown)

    if os.environ.get("FREECAD_MCP_DEBUG", "0") == "1":
        return _run_instrumented(extra)
    return _run_inprocess(extra)


if __name__ == "__main__":
    raise SystemExit(main())
