from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_rpc_startup_modules_import_from_freecad_addon_path() -> None:
    addon_dir = Path(__file__).parents[1] / "addon" / "FreeCADMCP"
    script = """
import sys

sys.path.insert(0, sys.argv[1])
import part3_collaboration.admission
import rpc_server.methods.cad_methods_ops.recompute_helpers
import rpc_server.methods.part3_collaboration_methods
"""

    completed = subprocess.run(
        [sys.executable, "-I", "-c", script, str(addon_dir)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
