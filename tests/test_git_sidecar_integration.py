"""Real-CLI integration test for the MCP Git sidecar adapter.

test_git_sidecar.py mocks subprocess.run, so it cannot catch a broken or
uninstalled freecad-git CLI: export_sidecar_after_save() would return
{"ok": False, "error": ...} and nothing surfaces that to a human (the
post-save observer's return value is never read). This test shells out to
the real CLI so that failure mode fails CI instead of failing silently on
someone's save.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from addon.FreeCADMCP.git_sidecar import export_sidecar_after_save

# tools/mcp/freecad-mcp/tests -> tools/freecad_git, both checked out together
# in the monorepo (this submodule has no direct dependency on freecad_git).
_FIXTURE = (
    Path(__file__).resolve().parents[3] / "freecad_git" / "tests" / "fixtures" / "basic.FCStd"
)


@pytest.mark.integration
@pytest.mark.skipif(
    not _FIXTURE.is_file(),
    reason="freecad_git fixtures not checked out alongside freecad-mcp",
)
def test_export_sidecar_after_save_runs_real_cli(tmp_path, monkeypatch):
    settings = tmp_path / "freecad_mcp_settings.json"
    settings.write_text(
        json.dumps({"generate_git_sidecar_after_save": True}), encoding="utf-8"
    )
    monkeypatch.setattr("addon.FreeCADMCP.git_sidecar._settings_path", lambda: settings)

    fcstd = tmp_path / "model.FCStd"
    shutil.copyfile(_FIXTURE, fcstd)
    sidecar = tmp_path / "model.FCStd.git.json"

    result = export_sidecar_after_save(str(fcstd))

    assert result == {"ok": True, "path": str(fcstd), "sidecar": str(sidecar)}
    assert sidecar.is_file(), "real CLI reported success but wrote no sidecar"
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert payload["generator"]["name"] == "freecad-git"
    assert "Box" in payload["objects"]
