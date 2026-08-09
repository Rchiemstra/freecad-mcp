#!/usr/bin/env python3
"""Bootstrap per-subject capability manifests from the frozen registry snapshot."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from tests.helpers.runtime_bootstrap import bootstrap_unit_test_runtime  # noqa: E402

bootstrap_unit_test_runtime()

from freecad_mcp.capabilities.bootstrap import (  # noqa: E402
    bootstrap_subject_manifests,
    write_subject_manifest_modules,
)


def main() -> int:
    manifests = bootstrap_subject_manifests()
    written = write_subject_manifest_modules(manifests)
    print(f"bootstrapped {len(written)} subject manifests")
    for path in written:
        print(f"  {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
