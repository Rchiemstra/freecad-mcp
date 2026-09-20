"""F-05: the runtime must be able to tie the loaded addon to a git commit.

Committed build metadata is always ``unknown`` in a development checkout (a file cannot
contain the hash of the commit that contains it), so ``get_runtime_info`` reported
``git_commit: "unknown"`` for the addon and "match cannot be verified". The addon now
records the checkout it was loaded from, and the MCP compares it with its own checkout.
"""

from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from addon.FreeCADMCP import build_info as addon_build_info
from freecad_mcp.server_ops.runtime_identity import identity_compatibility

pytestmark = pytest.mark.unit

COMMIT = "a8cd66d1bfaf1424ee774f330683c5112ec30a71"
UNKNOWN = {"build_id": "freecad-mcp-0.2.0+unknown", "git_commit": "unknown"}


def _fake_git(outputs: dict[str, str]):
    def run(args, **_kwargs):
        verb = args[3]
        if verb not in outputs:
            raise subprocess.CalledProcessError(128, args)
        return SimpleNamespace(stdout=outputs[verb])

    return run


def test_addon_reads_its_checkout(monkeypatch):
    monkeypatch.setattr(addon_build_info.subprocess, "run", _fake_git({"rev-parse": COMMIT + "\n", "status": ""}))
    assert addon_build_info.read_checkout_identity() == {
        "git_commit": COMMIT,
        "git_dirty": False,
        "available": True,
    }


def test_addon_reports_dirty_checkout(monkeypatch):
    monkeypatch.setattr(
        addon_build_info.subprocess, "run", _fake_git({"rev-parse": COMMIT, "status": " M addon/x.py\n"})
    )
    assert addon_build_info.read_checkout_identity()["git_dirty"] is True


def test_addon_without_git_is_unavailable(monkeypatch):
    monkeypatch.setattr(addon_build_info.subprocess, "run", _fake_git({}))
    assert addon_build_info.read_checkout_identity() == {
        "git_commit": "unknown",
        "git_dirty": None,
        "available": False,
    }


def test_as_dict_exposes_the_checkout_captured_at_load():
    checkout = addon_build_info.as_dict()["checkout"]
    assert set(checkout) == {"git_commit", "git_dirty", "available"}


def _checkout(commit: str = COMMIT, *, dirty: bool = False, available: bool = True) -> dict[str, object]:
    return {"git_commit": commit, "git_dirty": dirty, "available": available}


def test_matching_checkouts_verify_identity_when_compiled_metadata_is_unknown():
    identity = identity_compatibility(
        mcp_compiled=UNKNOWN,
        addon_compiled=UNKNOWN,
        mcp_checkout=_checkout(),
        addon_checkout=_checkout(),
    )
    assert identity["checkout_match"] is True
    assert not any("cannot be verified" in warning for warning in identity["warnings"])


def test_different_checkouts_are_reported():
    identity = identity_compatibility(
        mcp_compiled=UNKNOWN,
        addon_compiled=UNKNOWN,
        mcp_checkout=_checkout(),
        addon_checkout=_checkout("0" * 39 + "1"),
    )
    assert identity["checkout_match"] is False
    assert any("checkouts differ" in warning for warning in identity["warnings"])


def test_missing_addon_checkout_keeps_the_unverified_warning():
    identity = identity_compatibility(
        mcp_compiled=UNKNOWN,
        addon_compiled=UNKNOWN,
        mcp_checkout=_checkout(),
    )
    assert identity["checkout_match"] is None
    assert any("cannot be verified" in warning for warning in identity["warnings"])
