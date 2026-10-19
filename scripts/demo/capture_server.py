"""Recording-only MCP entry point with a deadline long enough for native recomputes.

Keep the stdio session alive through the entire take; a 150-second HTTP deadline
can close a slow request's socket before FreeCAD sends its result (BrokenPipe).
This changes only the client deadline, never retries an uncertain mutation.
"""
from freecad_mcp.freecad_client import FreeCADConnection
_original = FreeCADConnection.__init__
def _capture_init(self, *args, **kwargs):
    kwargs.setdefault('timeout', 600)
    _original(self, *args, **kwargs)
FreeCADConnection.__init__ = _capture_init
from freecad_mcp.server import main
main()
