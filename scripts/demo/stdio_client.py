"""Small synchronous facade over the real MCP SDK stdio transport."""
import asyncio
import json
import os
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

class Client:
    def __init__(self, workdir, timeout=180):
        self.timeout = timeout
        from mcp import StdioServerParameters
        self.workdir = Path(workdir)
        self.params = StdioServerParameters(
            command=sys.executable,
            args=['-m', 'freecad_mcp.server', '--only-text-feedback', '--instance-manifest', str(self.workdir / 'profile/instance-manifest.json')],
            cwd=str(ROOT), env=dict(os.environ, PYTHONPATH=str(ROOT / 'src')),
        )
        self.errlog = (self.workdir / 'mcp-stderr.log').open('a')
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()
        self.session = self.run(self.open())

    def run(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(self.timeout)

    async def open(self):
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client
        ready = self.loop.create_future()
        self.stop = asyncio.Event()
        async def hold():
            try:
                async with stdio_client(self.params, errlog=self.errlog) as streams:
                    async with ClientSession(*streams) as session:
                        await session.initialize()
                        ready.set_result(session)
                        await self.stop.wait()
            except BaseException as exc:
                if not ready.done():
                    ready.set_exception(exc)
                raise
        self.holder = asyncio.ensure_future(hold())
        return await ready

    def call(self, tool, **args):
        result = self.run(self.session.call_tool(tool, args))
        text = '\n'.join(getattr(c, 'text', '') for c in result.content).strip()
        data = getattr(result, 'structuredContent', None)
        if isinstance(data, dict):
            data = data.get('data', data)
            if isinstance(data,dict) and set(data)=={'value'}:
                data=data['value']
        else:
            try:
                data = json.loads(text)
                if isinstance(data, dict) and isinstance(data.get('message'), str):
                    try:
                        data = json.loads(data['message'])
                    except ValueError:
                        pass
            except ValueError:
                data = {}
        ok = not result.isError and not (isinstance(data, dict) and (data.get('success') is False or data.get('ok') is False))
        return {'ok': ok, 'text': text, 'data': data}

    def close(self):
        self.loop.call_soon_threadsafe(self.stop.set)
        async def finish():
            await self.holder
        self.run(finish())
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(5)
        self.errlog.close()
