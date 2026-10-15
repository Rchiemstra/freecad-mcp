"""Live GUI scenarios must work at local and CI checkout locations."""

from pathlib import Path

import pytest


@pytest.mark.unit
def test_live_gui_has_no_hardcoded_workspace_paths():
    live_gui = Path(__file__).parent / "live_gui"
    violations = [
        f"{path.relative_to(live_gui.parent)}:{number}: {line.strip()}"
        for path in sorted(live_gui.rglob("*.py"))
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if "/workspace" in line
    ]
    assert not violations, "Hardcoded local mount paths:\n" + "\n".join(violations)
