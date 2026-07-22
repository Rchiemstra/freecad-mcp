#!/usr/bin/env python3
"""Isolated mutation-authority coupling / soft-compat test entrypoint.

Modes:
  default / --coupling   Require patched FreeCAD from freecad-build stage.
  --soft-compat          Stock FreeCAD; core API absence is OK.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import traceback
from pathlib import Path


REPORT_PATH = Path(
    os.environ.get("MUTATION_AUTHORITY_REPORT", "/tmp/mutation_authority_report.json")
)


def _run(cmd: list[str], *, cwd: str | None = None) -> dict:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return {
        "cmd": cmd,
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "")[-12000:],
        "stderr": (proc.stderr or "")[-6000:],
        "ok": proc.returncode == 0,
    }


def _verify_patched_runtime() -> dict:
    result = {
        "name": "verify_patched_freecad_runtime",
        "ok": False,
        "checks": {},
        "error": None,
    }
    try:
        freecadcmd = subprocess.check_output(["command", "-v", "FreeCADCmd"], text=True).strip()
    except Exception:
        # Windows / non-bash: use shutil
        import shutil

        freecadcmd = shutil.which("FreeCADCmd") or ""
    result["checks"]["freecadcmd_path"] = freecadcmd
    prefix = os.environ.get("FREECAD_HOME", "/opt/freecad-mutation-authority")
    result["checks"]["expected_prefix"] = prefix
    if not freecadcmd.startswith(prefix):
        result["error"] = f"FreeCADCmd not from patched prefix: {freecadcmd}"
        return result

    probe = _run(
        [
            sys.executable,
            "-c",
            "import FreeCAD, os, sys;\n"
            "print('FreeCAD.__file__=', FreeCAD.__file__);\n"
            "assert FreeCAD.__file__.startswith(os.environ.get('FREECAD_HOME','/opt/freecad-mutation-authority'));\n"
            "d=FreeCAD.newDocument('AuthProbe');\n"
            "assert callable(getattr(d,'openMutationCapability', None)), 'missing openMutationCapability';\n"
            "FreeCAD.closeDocument(d.Name);\n"
            "print('PATCHED_API_OK');\n",
        ]
    )
    result["checks"]["python_probe"] = probe
    if not probe["ok"] or "PATCHED_API_OK" not in probe["stdout"]:
        result["error"] = "Patched FreeCAD Python modules missing mutation authority API"
        return result
    result["ok"] = True
    return result


def _run_gtest() -> dict:
    exe = os.path.join(
        os.environ.get("FREECAD_HOME", "/opt/freecad-mutation-authority"),
        "bin",
        "App_tests_run",
    )
    if not os.path.isfile(exe):
        return {
            "name": "DocumentMutationAuthority_gtest",
            "ok": False,
            "error": f"missing {exe}",
        }
    out = _run([exe, "--gtest_filter=DocumentMutationAuthority*"])
    out["name"] = "DocumentMutationAuthority_gtest"
    out["executable"] = exe
    return out


def _run_pytest_core_authority() -> dict:
    out = _run(
        [sys.executable, "-m", "pytest", "tests/test_core_authority.py", "-ra", "--tb=short"],
        cwd="/workspace",
    )
    out["name"] = "freecad_mcp_core_authority_unit"
    return out


def _live_coupling_checks(*, require_core: bool) -> dict:
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
        result["error"] = f"FreeCAD unavailable: {exc}"
        result["ok"] = not require_core
        result["skipped"] = not require_core
        return result

    module_path = getattr(FreeCAD, "__file__", "")
    result["checks"].append({"FreeCAD.__file__": module_path})
    if require_core:
        prefix = os.environ.get("FREECAD_HOME", "/opt/freecad-mutation-authority")
        if not str(module_path).startswith(prefix):
            result["error"] = f"FreeCAD module not from patched build: {module_path}"
            return result

    doc = FreeCAD.newDocument("MutationAuthorityCoupling")
    try:
        if not callable(getattr(doc, "openMutationCapability", None)):
            if require_core:
                result["error"] = "openMutationCapability missing (coupling mode requires patched FreeCAD)"
                return result
            result["skipped"] = True
            result["error"] = "DocumentMutationAuthority API not present (soft-compat)"
            result["ok"] = True
            return result

        doc.setMutationOwner("mcp", 1, "docker-coupling")
        denied = False
        try:
            doc.addObject("App::FeatureTest", "ShouldFail")
        except Exception as exc:
            denied = ("Mutation denied" in str(exc)) or ("DENY" in str(exc))
        result["checks"].append({"core_deny_without_capability": denied})

        allowed = False
        try:
            cap = doc.openMutationCapability(None, 1)
            doc.addObject("App::FeatureTest", "ShouldPass")
            del cap
            allowed = True
        except Exception as exc:
            result["checks"].append({"capability_allow_error": str(exc)})
        result["checks"].append({"capability_allows_mutation": allowed})

        # Generation above 2^32
        large = (1 << 33) + 7
        doc.clearMutationOwner()
        doc.setMutationOwner("mcp", large, "docker-coupling")
        status = dict(doc.mutationAuthorityStatus())
        large_ok = int(status.get("generation", 0)) == large
        result["checks"].append({"generation_above_2_32": large_ok, "status": status})

        # Revocation: clear + re-own same generation
        cap = doc.openMutationCapability(None, large)
        doc.clearMutationOwner()
        doc.setMutationOwner("mcp", large, "docker-coupling")
        revoked = False
        try:
            doc.addObject("App::FeatureTest", "OldCapShouldFail")
        except Exception:
            revoked = True
        del cap
        result["checks"].append({"clear_reown_revokes_old_cap": revoked})

        new_gen = doc.bumpMutationGeneration()
        status = dict(doc.mutationAuthorityStatus())
        takeover_ok = status.get("owner") == "user" and int(new_gen) > large
        try:
            doc.addObject("App::FeatureTest", "UserOwnedOk")
            user_ok = True
        except Exception:
            user_ok = False
        result["checks"].append(
            {
                "takeover_fencing": takeover_ok,
                "user_owned_allows_local": user_ok,
            }
        )

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
                large_ok,
                revoked,
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--soft-compat",
        action="store_true",
        help="Stock FreeCAD mode; core API absence is allowed",
    )
    parser.add_argument(
        "--coupling",
        action="store_true",
        help="Require patched FreeCAD from freecad-build (default)",
    )
    args = parser.parse_args(argv)

    require_core = not args.soft_compat
    if os.environ.get("MUTATION_AUTHORITY_REQUIRE_CORE") == "0":
        require_core = False
    if args.coupling:
        require_core = True

    report = {
        "environment": {
            "mutation_authority_coupling": os.environ.get("MUTATION_AUTHORITY_COUPLING"),
            "require_core": require_core,
            "freecad_home": os.environ.get("FREECAD_HOME"),
            "python": sys.version,
            "executable": sys.executable,
        },
        "results": [],
    }

    report["results"].append(_run_pytest_core_authority())
    if require_core:
        report["results"].append(_verify_patched_runtime())
        report["results"].append(_run_gtest())
    report["results"].append(_live_coupling_checks(require_core=require_core))

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))

    failed = [item for item in report["results"] if not item.get("ok")]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
