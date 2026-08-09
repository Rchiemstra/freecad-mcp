#!/usr/bin/env python3
"""One-shot migration: emit generated register modules and declarative shims."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from freecad_mcp.capabilities.bootstrap import load_frozen_registry_snapshot
from freecad_mcp.capabilities.generator import (
    render_inline_tools_runtime_info_shim,
    render_register_module_shim,
    write_register_module_outputs,
)


def main() -> int:
    snapshot = load_frozen_registry_snapshot()
    register_modules = tuple(snapshot["register_order"])
    paths = write_register_module_outputs(register_modules=register_modules)
    print(f"generated {len(paths)} register-module artifacts")

    pkg = ROOT / "src" / "freecad_mcp"
    for name in register_modules:
        (pkg / f"{name}.py").write_text(
            render_register_module_shim(name),
            encoding="utf-8",
        )

    inline_pkg = pkg / "capabilities" / "inline"
    inline_pkg.mkdir(parents=True, exist_ok=True)
    (inline_pkg / "__init__.py").write_text(
        '"""Inline tool references for manifest bootstrap fallbacks."""\n\n'
        "from __future__ import annotations\n\n"
        "__all__: list[str] = []\n",
        encoding="utf-8",
    )
    (inline_pkg / "tools_runtime_info.py").write_text(
        render_inline_tools_runtime_info_shim(),
        encoding="utf-8",
    )

    inline_py = pkg / "capabilities" / "inline.py"
    if inline_py.is_file():
        inline_py.unlink()
        print("removed capabilities/inline.py module file")

    print(f"shimmed {len(register_modules)} register modules")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
