"""Create hard-link or copy aliases for worker document loading."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any


def materialize_load_aliases(snapshot: dict[str, Any]) -> None:
    """Create exact-name aliases outside the GUI thread for document identity."""
    for entry in snapshot["documents"]:
        source = Path(entry["snapshot_path"])
        target = Path(entry["load_path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(source, target)
        except OSError:
            shutil.copy2(source, target)
