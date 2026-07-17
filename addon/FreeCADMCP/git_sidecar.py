"""Opt-in MCP post-save Git sidecar adapter.

Invokes the standalone freecad-git CLI/package — no serialization logic is duplicated here.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

_active_exports: set[str] = set()
_lock = threading.Lock()


def _settings_path() -> Path:
    try:
        import FreeCAD

        return Path(FreeCAD.getUserAppDataDir()) / "freecad_mcp_settings.json"
    except ImportError:
        return Path.home() / "freecad_mcp_settings.json"


def is_enabled() -> bool:
    """Return True when MCP Git sidecar generation is enabled."""
    path = _settings_path()
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return bool(data.get("generate_git_sidecar_after_save", False))
    except (OSError, json.JSONDecodeError):
        return False


def _is_eligible_target(filename: str) -> bool:
    path = Path(filename)
    name_lower = path.name.lower()
    if not name_lower.endswith(".fcstd"):
        return False
    for pattern in (".fcstd1", ".fcstd2", ".bak", ".tmp", ".recovery", "mcp_snap_", "~"):
        if pattern in name_lower:
            return False
    parts = {p.lower() for p in path.parts}
    if parts & {"fc_recovery_files", "recovery", "autosave", "snapshots", "snapshot"}:
        return False
    return True


def _find_freecad_git() -> list[str]:
    """Build command to invoke freecad-git."""
    if sys.platform == "win32":
        python = Path(sys.prefix) / "python.exe"
    else:
        python = Path(sys.prefix) / "bin" / "python"

    # Embedded FreeCAD reports FreeCAD.exe as sys.executable. Prefer the real
    # interpreter from the same environment so Python's ``-m`` option works.
    executable = str(python) if python.is_file() else sys.executable
    return [executable, "-m", "freecad_git.cli", "export"]


def _subprocess_creation_flags() -> int:
    """Suppress the transient Python console window on Windows."""
    if sys.platform == "win32":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0


def export_sidecar_after_save(filename: str) -> dict[str, Any]:
    """Generate sidecar after confirmed successful save. Returns structured result."""
    if not is_enabled():
        return {"ok": False, "skipped": True, "reason": "disabled"}

    if not _is_eligible_target(filename):
        return {"ok": False, "skipped": True, "reason": "ineligible_target"}

    canonical = str(Path(filename).resolve())
    with _lock:
        if canonical in _active_exports:
            return {"ok": False, "skipped": True, "reason": "already_active"}
        _active_exports.add(canonical)

    sidecar = f"{filename}.git.json"
    try:
        cmd = _find_freecad_git() + [filename]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            creationflags=_subprocess_creation_flags(),
        )
        if proc.returncode != 0:
            return {
                "ok": False,
                "error": proc.stderr.strip() or proc.stdout.strip() or "export failed",
                "path": filename,
                "sidecar": sidecar,
            }
        if not Path(sidecar).is_file():
            return {
                "ok": False,
                "error": "sidecar file was not written",
                "path": filename,
                "sidecar": sidecar,
            }
        return {"ok": True, "path": filename, "sidecar": sidecar}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "sidecar export timed out", "path": filename}
    except OSError as exc:
        return {"ok": False, "error": str(exc), "path": filename}
    finally:
        with _lock:
            _active_exports.discard(canonical)


class McpGitSidecarObserver:
    """Document observer for MCP post-save sidecar generation."""

    def slotFinishSaveDocument(self, document, filename):
        if not is_enabled():
            return
        result = export_sidecar_after_save(filename)
        if not result.get("ok") and not result.get("skipped"):
            try:
                import FreeCAD

                FreeCAD.Console.PrintWarning(
                    f"MCP Git sidecar failed for {filename}: {result.get('error', 'unknown')}\n"
                )
            except ImportError:
                pass


_observer_registered = False


def register_observer() -> None:
    """Register MCP Git sidecar observer with FreeCAD."""
    global _observer_registered
    if _observer_registered:
        return
    try:
        import FreeCAD

        observer = McpGitSidecarObserver()
        FreeCAD.addDocumentObserver(observer)
        FreeCAD._mcp_git_sidecar_observer = observer
        _observer_registered = True
    except ImportError:
        pass
