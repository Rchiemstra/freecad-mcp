"""Run ``ci/qualify_<op>.py --native`` under FreeCADCmd.

Set ``FREECAD_MCP_QUALIFY_OP`` to the operation stem (e.g. ``sweep_feature``).
"""

from __future__ import annotations

import os
import runpy
import sys

op = os.environ.get("FREECAD_MCP_QUALIFY_OP", "").strip()
if not op:
    raise SystemExit("FREECAD_MCP_QUALIFY_OP is required (e.g. sweep_feature)")
qualify = f"ci/qualify_{op}.py"
os.environ["FREECAD_MCP_REQUIRE_NATIVE_COLLABORATION"] = "1"
sys.argv = [qualify, "--native"]
result = runpy.run_path(qualify, run_name="__main__")
raise SystemExit(result if isinstance(result, int) else 0)
