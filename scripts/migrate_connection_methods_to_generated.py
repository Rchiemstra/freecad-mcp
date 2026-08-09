#!/usr/bin/env python3
"""One-shot migration: emit generated connection methods and declarative shims."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from freecad_mcp.capabilities.generator import (
    connection_method_module_names,
    render_connection_method_shim,
    render_connection_methods_package_init,
    write_connection_method_outputs,
)


def main() -> int:
    module_names = connection_method_module_names()
    paths = write_connection_method_outputs()
    print(f"generated {len(paths)} connection-method artifacts")

    methods_dir = ROOT / "src" / "freecad_mcp" / "freecad_client_ops" / "connection_methods"
    for name in module_names:
        (methods_dir / f"{name}.py").write_text(
            render_connection_method_shim(name),
            encoding="utf-8",
        )
    (methods_dir / "__init__.py").write_text(
        render_connection_methods_package_init(module_names),
        encoding="utf-8",
    )

    print(f"shimmed {len(module_names)} connection method modules")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
