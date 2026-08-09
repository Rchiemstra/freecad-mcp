"""Refresh architecture_policy_allowances.json from current scan (integrator gate)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ci"))

from lint_python import (  # noqa: E402
    ALLOWANCE_FILE,
    allowance_records,
    discover_files,
    scan_architecture,
)


def main() -> int:
    root = ROOT.resolve()
    files = discover_files(["addon/FreeCADMCP", "src/freecad_mcp"], root, [])
    findings = scan_architecture(files, root)
    records = allowance_records(findings)
    payload = {"schema_version": 1, "allowances": records}
    ALLOWANCE_FILE.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(records)} allowances to {ALLOWANCE_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
