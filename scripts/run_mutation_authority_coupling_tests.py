#!/usr/bin/env python3
"""Entrypoint for Part-12 mutation-authority coupling tests inside Docker.

Runs:
  1. freecad-mcp soft-compat / unit bridge tests (always)
  2. Live FreeCAD coupling checks when DocumentMutationAuthority is present
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import traceback
from pathlib import Path


REPORT_PATH = Path(os.environ.get("MUTATION_AUTHORITY_REPORT", "/tmp/mutation_authority_report.json"))


def _run_pytest() -> dict:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_core_authority.py",
        "-ra",
        "--tb=short",
    ]
    proc = subprocess.run(cmd, cwd="/workspace", capture_output=True, text=True)
    return {
        "name": "freecad_mcp_core_authority_unit",
        "returncode": proc.returncode,
        "stdout": proc.stdout[-8000:],
        "stderr": proc.stderr[-4000:],
        "ok": proc.returncode == 0,
    }


def _live_coupling_checks() -> dict:
    result = {
        "name": "live_freecad_mutation_authority",
        "ok": False,
        "skipped": False,
        "checks": [],
        "error": None,
    }
    try:
        import FreeCAD  # type: ignore
    except Exception as exc:
        result["skipped"] = True
        result["error"] = f"FreeCAD unavailable: {exc}"
        result["ok"] = True  # soft-compat image may still pass unit tests
        return result

    doc = FreeCAD.newDocument("MutationAuthorityCoupling")
    try:
        if not callable(getattr(doc, "openMutationCapability", None)):
            result["skipped"] = True
            result["error"] = "DocumentMutationAuthority API not present (stock FreeCAD)"
            result["ok"] = True
            return result

        # 1. Core enforcement: denied without capability
        doc.setMutationOwner("mcp", 1, "docker-coupling")
        denied = False
        try:
            doc.addObject("App::FeatureTest", "ShouldFail")
        except Exception as exc:
            denied = ("Mutation denied" in str(exc)) or ("DENY" in str(exc))
        result["checks"].append({"core_deny_without_capability": denied})

        # 2. Valid capability allows mutation
        allowed = False
        try:
            cap = doc.openMutationCapability(None, 1)
            doc.addObject("App::FeatureTest", "ShouldPass")
            del cap
            allowed = True
        except Exception as exc:
            result["checks"].append({"capability_allow_error": str(exc)})
        result["checks"].append({"capability_allows_mutation": allowed})

        # 3. Stale generation rejected
        stale_denied = False
        try:
            bad = doc.openMutationCapability(None, 99)
            stale_denied = bad is None
        except Exception:
            stale_denied = True
        result["checks"].append({"stale_generation_rejected": stale_denied})

        # 4. Takeover fencing
        new_gen = doc.bumpMutationGeneration()
        status = dict(doc.mutationAuthorityStatus())
        takeover_ok = status.get("owner") == "user" and int(new_gen) >= 2
        # After takeover, local mutation works without MCP capability
        try:
            doc.addObject("App::FeatureTest", "UserOwnedOk")
            user_ok = True
        except Exception:
            user_ok = False
        result["checks"].append(
            {
                "takeover_fencing": takeover_ok,
                "user_owned_allows_local": user_ok,
                "status": status,
            }
        )

        # 5. Multi-document isolation
        other = FreeCAD.newDocument("MutationAuthorityOther")
        try:
            doc.setMutationOwner("mcp", 5, "docker-coupling")
            other.setMutationOwner("mcp", 5, "docker-coupling")
            cap = doc.openMutationCapability(None, 5)
            doc.addObject("App::FeatureTest", "DocAOnly")
            cross_denied = False
            try:
                other.addObject("App::FeatureTest", "CrossLeak")
            except Exception:
                cross_denied = True
            del cap
            result["checks"].append({"multi_document_no_cross_leak": cross_denied})
        finally:
            other.clearMutationOwner()
            FreeCAD.closeDocument(other.Name)

        result["ok"] = all(
            (
                denied,
                allowed,
                stale_denied,
                takeover_ok,
                user_ok,
                cross_denied,
            )
        )
    except Exception as exc:
        result["error"] = f"{exc}\n{traceback.format_exc()}"
        result["ok"] = False
    finally:
        try:
            if callable(getattr(doc, "clearMutationOwner", None)):
                doc.clearMutationOwner()
        except Exception:
            pass
        try:
            FreeCAD.closeDocument(doc.Name)
        except Exception:
            pass
    return result


def main() -> int:
    report = {
        "environment": {
            "mutation_authority_coupling": os.environ.get("MUTATION_AUTHORITY_COUPLING"),
            "python": sys.version,
        },
        "results": [],
    }
    report["results"].append(_run_pytest())
    report["results"].append(_live_coupling_checks())

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))

    failed = [item for item in report["results"] if not item.get("ok")]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
