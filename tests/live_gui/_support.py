"""Shared pieces of the live FreeCAD GUI + MCP tests (see conftest.py)."""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import threading
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MCP_ROOT = Path(__file__).resolve().parents[2]
CALL_TIMEOUT = 180.0
_PROBLEM = re.compile(
    r"warn|wrn|error|err:|exception|traceback|segmentation|abort|qobject::|qwidget::"
    r"|qpainter::|coin |would ?block|fatal|critical",
    re.IGNORECASE,
)
_ALWAYS_ALLOWED = (re.compile(r"SplashWarningColor"),)


@dataclass
class ToolResult:
    tool: str
    is_error: bool
    text: str
    payload: dict[str, Any] | None

    @property
    def ok(self) -> bool:
        return not self.is_error and (
            self.payload is None or self.payload.get("success") is not False
        )


def _payload(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
    except ValueError:
        return None
    if isinstance(value, dict) and isinstance(value.get("message"), str):
        try:
            inner = json.loads(value["message"])
        except ValueError:
            inner = None
        if isinstance(inner, dict):
            return inner
    return value if isinstance(value, dict) else None


class McpClient:
    """One MCP stdio session kept open on a private event loop thread."""

    def __init__(self, manifest: Path, workdir: Path) -> None:
        from mcp import StdioServerParameters

        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(
            [str(MCP_ROOT / "src"), *filter(None, [env.get("PYTHONPATH")])]
        )
        self._params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "freecad_mcp.server", "--instance-manifest", str(manifest)],
            cwd=str(workdir),
            env=env,
        )
        self._errlog = open(workdir / "mcp_server.log", "a", encoding="utf-8")
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        self._stop: asyncio.Event | None = None
        self._holder: asyncio.Future[None] | None = None
        self._session = self._run(self._open(), timeout=120.0)

    def _run(self, coroutine, timeout: float = CALL_TIMEOUT):
        return asyncio.run_coroutine_threadsafe(coroutine, self._loop).result(timeout)

    async def _open(self):
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client

        ready: asyncio.Future = self._loop.create_future()
        self._stop = asyncio.Event()

        async def hold() -> None:
            try:
                async with stdio_client(self._params, errlog=self._errlog) as streams:
                    async with ClientSession(*streams) as session:
                        await session.initialize()
                        ready.set_result(session)
                        await self._stop.wait()
            except BaseException as exc:
                if not ready.done():
                    ready.set_exception(exc)
                raise

        self._holder = asyncio.ensure_future(hold())
        return await ready

    async def _call(self, tool: str, args: dict[str, Any]) -> ToolResult:
        result = await self._session.call_tool(tool, args)
        text = " ".join(getattr(item, "text", "") for item in result.content).strip()
        return ToolResult(tool, bool(result.isError), text, _payload(text))

    def call(self, tool: str, **args: Any) -> ToolResult:
        return self._run(self._call(tool, args))

    def parallel(self, calls: Iterable[tuple[str, dict[str, Any]]]) -> list[ToolResult]:
        async def gather():
            return await asyncio.gather(*(self._call(tool, args) for tool, args in calls))

        return self._run(gather())

    def close(self) -> None:
        if self._stop is not None:
            self._loop.call_soon_threadsafe(self._stop.set)
        if self._holder is not None:
            try:
                self._run(asyncio.wait_for(asyncio.shield(self._holder), 30.0), timeout=40.0)
            except Exception:
                pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(10)
        self._errlog.close()


class GuiLog:
    """FreeCAD output since the start of the current test."""

    def __init__(self, paths: list[Path]) -> None:
        self._paths = paths
        self.reset()

    def reset(self) -> None:
        """Only report output produced after this call."""
        self._offsets = {path: self._size(path) for path in self._paths}

    @staticmethod
    def _size(path: Path) -> int:
        return path.stat().st_size if path.exists() else 0

    def problems(self, allowed: Iterable[str] = ()) -> list[str]:
        patterns = [*_ALWAYS_ALLOWED, *(re.compile(pattern) for pattern in allowed)]
        lines = []
        for path in self._paths:
            if not path.exists():
                continue
            with path.open(encoding="utf-8", errors="replace") as stream:
                stream.seek(self._offsets[path])
                lines.extend(stream.read().splitlines())
        return [
            line
            for line in lines
            if _PROBLEM.search(line) and not any(p.search(line) for p in patterns)
        ]


def assert_ok(result: ToolResult) -> ToolResult:
    assert result.ok, f"{result.tool} failed: {result.text[:600]}"
    return result


def assert_clean(gui_log: GuiLog, *allowed: str) -> None:
    problems = gui_log.problems(allowed)
    assert not problems, "FreeCAD printed warnings/errors:\n" + "\n".join(problems[:40])
