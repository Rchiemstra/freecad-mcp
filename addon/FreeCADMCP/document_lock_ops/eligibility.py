from __future__ import annotations

from pathlib import Path


def _is_eligible_target(filename: str) -> bool:
    """Skip recovery/snapshot/backup paths — never lock those files."""
    try:
        from git_sidecar import _is_eligible_target as _git_eligible

        return _git_eligible(filename)
    except ImportError:
        path = Path(filename)
        name_lower = path.name.lower()
        if not name_lower.endswith(".fcstd"):
            return False
        for pattern in (".fcstd1", ".fcstd2", ".bak", ".tmp", ".recovery", "mcp_snap_", "~"):
            if pattern in name_lower:
                return False
        parts = {p.lower() for p in path.parts}
        return not parts & {"fc_recovery_files", "recovery", "autosave", "snapshots", "snapshot"}
