"""Runtime identity helpers for get_runtime_info (compiled vs checkout)."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

_COMPILED_SOURCE_GENERATED = "generated_metadata"
_COMPILED_SOURCE_ENVIRONMENT = "environment"
_COMPILED_SOURCE_MISSING = "missing"

_PATH_SHAPED_COMMIT = re.compile(
    r"^(?:/proc/|[a-zA-Z]:[/\\]|https?://|.*\.exe$)",
    re.IGNORECASE,
)


def is_path_shaped_git_commit(value: object) -> bool:
    rendered = str(value).strip() if value is not None else ""
    if not rendered or rendered == "unknown":
        return False
    if "/" in rendered or "\\" in rendered:
        return True
    return bool(_PATH_SHAPED_COMMIT.search(rendered))


def sanitize_git_commit(value: object) -> str:
    rendered = str(value).strip() if value is not None else ""
    if not rendered:
        return "unknown"
    if is_path_shaped_git_commit(rendered):
        return "unknown"
    return rendered


def is_unknown_build_id(build_id: object) -> bool:
    rendered = str(build_id or "").strip()
    return not rendered or rendered.endswith("+unknown")


def is_unknown_git_commit(git_commit: object) -> bool:
    rendered = sanitize_git_commit(git_commit)
    return rendered == "unknown"


def _find_git_root(start: Path) -> Path | None:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _git_root() -> Path | None:
    return _find_git_root(Path(__file__))


def _optional_bool(value: object) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "dirty"}:
        return True
    if normalized in {"0", "false", "no", "clean"}:
        return False
    return None


def read_checkout_git() -> dict[str, Any]:
    root = _git_root()
    if root is None:
        return {"git_commit": "unknown", "git_dirty": None, "available": False}
    try:
        commit = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        dirty = bool(status.strip())
        return {
            "git_commit": sanitize_git_commit(commit),
            "git_dirty": dirty,
            "available": True,
        }
    except (OSError, subprocess.CalledProcessError):
        return {"git_commit": "unknown", "git_dirty": None, "available": False}


def identity_compatibility(
    *,
    mcp_compiled: dict[str, Any],
    addon_compiled: dict[str, Any],
    mcp_checkout: dict[str, Any],
    addon_checkout: dict[str, Any] | None = None,
) -> dict[str, Any]:
    warnings: list[str] = []
    checkout_match = _checkout_match(mcp_checkout, addon_checkout)
    mcp_build_id = str(mcp_compiled.get("build_id") or "")
    addon_build_id = str(addon_compiled.get("build_id") or "")
    mcp_commit = sanitize_git_commit(mcp_compiled.get("git_commit"))
    addon_commit = sanitize_git_commit(addon_compiled.get("git_commit"))

    mcp_build_known = not is_unknown_build_id(mcp_build_id)
    addon_build_known = not is_unknown_build_id(addon_build_id)
    mcp_commit_known = not is_unknown_git_commit(mcp_commit)
    addon_commit_known = not is_unknown_git_commit(addon_commit)

    unknown_unmatched = (
        not mcp_build_known
        and not addon_build_known
        and not mcp_commit_known
        and not addon_commit_known
    )
    if unknown_unmatched and checkout_match is None:
        warnings.append(
            "Compiled MCP and addon identities are both unknown; match cannot be verified"
        )
    if checkout_match is False:
        warnings.append(
            "MCP and addon checkouts differ; the running addon was loaded from another commit"
        )
    if checkout_match and (mcp_checkout.get("git_dirty") or (addon_checkout or {}).get("git_dirty")):
        warnings.append(
            "Checkout has uncommitted changes; the commit identifies the base, not the exact code"
        )

    if mcp_commit_known and addon_commit_known and mcp_commit != addon_commit:
        warnings.append(
            "Compiled MCP and addon git commits differ; verify the running addon "
            "matches the intended build"
        )

    if mcp_build_known and addon_build_known and mcp_build_id != addon_build_id:
        warnings.append(
            "MCP package and FreeCAD addon build IDs differ; protocol compatibility "
            "permits this connection"
        )

    commits_comparable = mcp_commit_known and addon_commit_known
    builds_comparable = mcp_build_known and addon_build_known
    commit_ok = (not commits_comparable) or mcp_commit == addon_commit
    build_ok = (not builds_comparable) or mcp_build_id == addon_build_id
    mcp_addon = (
        not unknown_unmatched
        and commit_ok
        and build_ok
        and (commits_comparable or builds_comparable)
    )

    compiled_checkout = False
    if mcp_checkout.get("available"):
        checkout_commit = sanitize_git_commit(mcp_checkout.get("git_commit"))
        if (
            not is_unknown_git_commit(mcp_commit)
            and not is_unknown_git_commit(checkout_commit)
            and checkout_commit == mcp_commit
        ):
            compiled_checkout = True
        elif (
            not is_unknown_git_commit(mcp_commit)
            and not is_unknown_git_commit(checkout_commit)
            and checkout_commit != mcp_commit
        ):
            warnings.append(
                "Checkout commit differs from compiled MCP commit; verify the running "
                "process matches the intended checkout"
            )

    return {
        "mcp_addon": mcp_addon,
        "compiled_checkout": compiled_checkout,
        "unknown_unmatched": unknown_unmatched,
        "checkout_match": checkout_match,
        "warnings": warnings,
    }


def _checkout_match(
    mcp_checkout: dict[str, Any], addon_checkout: dict[str, Any] | None
) -> bool | None:
    """True/False when both checkouts name a commit; None when either is unavailable."""
    if not addon_checkout or not addon_checkout.get("available") or not mcp_checkout.get("available"):
        return None
    mcp_commit = sanitize_git_commit(mcp_checkout.get("git_commit"))
    addon_commit = sanitize_git_commit(addon_checkout.get("git_commit"))
    if is_unknown_git_commit(mcp_commit) or is_unknown_git_commit(addon_commit):
        return None
    return mcp_commit == addon_commit


def merge_compatibility(
    protocol: dict[str, Any],
    identity: dict[str, Any],
) -> dict[str, Any]:
    warnings = list(protocol.get("warnings") or [])
    for warning in identity.get("warnings") or ():
        if warning not in warnings:
            warnings.append(warning)
    return {
        "compatible": protocol.get("compatible", False),
        "warnings": warnings,
        "identity": {
            "mcp_addon": identity.get("mcp_addon", False),
            "compiled_checkout": identity.get("compiled_checkout", False),
            "unknown_unmatched": identity.get("unknown_unmatched", False),
            "checkout_match": identity.get("checkout_match"),
        },
    }
