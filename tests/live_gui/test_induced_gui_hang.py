"""Opt-in check that a stuck GUI thread is dumped and the run fails.

Marked ``hang_check`` so collection does not treat it as a unit test, and
not marked ``live_gui``, so neither CI suite selects it. Run it on purpose::

    FREECAD_MCP_LIVE_GUI_HANG_CHECK=1 xvfb-run -a python3 -m pytest \\
        tests/live_gui/test_induced_gui_hang.py -p no:cacheprovider --tb=short

The call sleeps on FreeCAD's GUI thread for far longer than the RPC deadline.
The harness must fail this test, print native stacks, and show that thread in
the sleep.
"""

from __future__ import annotations

import os
import time

import pytest

pytestmark = pytest.mark.hang_check


def test_induced_gui_hang_dumps_stacks(mcp):
    if os.environ.get("FREECAD_MCP_LIVE_GUI_HANG_CHECK") != "1":
        pytest.skip("set FREECAD_MCP_LIVE_GUI_HANG_CHECK=1 to block the GUI thread")
    print(f"INDUCED_HANG_START {time.time():.3f}", flush=True)
    # execution_mode=gui and no timeout_seconds: timeout_seconds is rejected on
    # the GUI thread, and this sleep is not interruptible once it starts.
    result = mcp.call(
        "execute_code",
        code="import time\ntime.sleep(100000)\n",
        execution_mode="gui",
    )
    pytest.fail(f"execute_code returned; FreeCAD was not treated as hung: {result.text[:800]}")
