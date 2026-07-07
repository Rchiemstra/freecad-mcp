
import sys
from pathlib import Path

import FreeCAD as App


def _ensure_freecad_mcp_package_path():
    for raw_path in list(sys.path):
        try:
            addon_path = Path(raw_path).resolve()
        except (OSError, TypeError):
            continue

        if addon_path.name == "FreeCADMCP" and addon_path.parent.name == "addon":
            package_src = addon_path.parent.parent / "src"
            if package_src.exists():
                package_src_text = str(package_src)
                if package_src_text not in sys.path:
                    sys.path.insert(0, package_src_text)
                return

    try:
        package_src = Path(__file__).resolve().parents[2] / "src"
    except (NameError, IndexError, OSError):
        return

    if package_src.exists():
        package_src_text = str(package_src)
        if package_src_text not in sys.path:
            sys.path.insert(0, package_src_text)


try:
    _ensure_freecad_mcp_package_path()
    from freecad_mcp.assembly_api_bootstrap import install as _install_assembly_api

    _install_assembly_api()
except Exception as exc:
    App.Console.PrintWarning(f"[FreeCADMCP] Assembly API bootstrap failed: {exc}\n")
