"""Execute one worker job inside an isolated FreeCADCmd process."""

from __future__ import annotations

import contextlib
import sys
import time
import traceback

import FreeCAD

try:
    from worker_protocol import (
        CappedTextWriter,
        read_json_limited,
        validate_job,
        write_json_atomic,
    )
except ImportError:
    from ..worker_protocol import (
        CappedTextWriter,
        read_json_limited,
        validate_job,
        write_json_atomic,
    )

from .artifact_emitter import ArtifactEmitter
from .link_validation_post import _attach_link_warnings
from .run_job_snapshot import (
    apply_recompute_option,
    open_snapshot_documents,
    validate_snapshot_links,
)
from .worker_builtins import worker_builtins


def job_path_from_argv(argv: list[str]) -> str:
    if "--pass" not in argv:
        raise ValueError("worker job must be provided after --pass")
    values = argv[argv.index("--pass") + 1 :]
    if len(values) != 1:
        raise ValueError("worker requires exactly one job JSON path after --pass")
    return values[0]


def run_job(job_path: str) -> int:
    job = read_json_limited(job_path)
    result_path = job.get("result_path")
    started = time.monotonic()
    writer = CappedTextWriter()
    opened: list[str] = []
    result = {
        "schema_version": 1,
        "job_id": job.get("job_id", "unknown"),
        "status": "error",
        "stdout": "",
        "stdout_truncated": False,
        "session": {},
        "error": None,
        "traceback": None,
        "artifacts": [],
        "metrics": {},
    }
    link_validation_warnings: list[str] = []
    try:
        validate_job(job)
        if job["kind"] == "probe":
            result["status"] = "ok"
            result["session"] = {"freecad_version": list(FreeCAD.Version())}
            return 0
        snapshot = job["snapshot"]
        opened, primary = open_snapshot_documents(snapshot)
        link_validation_warnings = validate_snapshot_links(snapshot, result)
        apply_recompute_option(primary, job.get("options") or {})

        emitter = ArtifactEmitter(job["artifact_directory"], primary)
        namespace = {
            "__builtins__": worker_builtins(),
            "__name__": "__mcp_worker_job__",
            "FreeCAD": FreeCAD,
            "App": FreeCAD,
            "emit_artifact": emitter,
        }
        with contextlib.redirect_stdout(writer):
            exec(job["code"], namespace)
        result["status"] = "ok"
        result["artifacts"] = emitter.artifacts
        session = {
            "active_document_after": (
                FreeCAD.ActiveDocument.Name if FreeCAD.ActiveDocument else None
            ),
            "documents": sorted(FreeCAD.listDocuments().keys()),
            "worker_read_only_snapshot": True,
        }
        if link_validation_warnings:
            result["link_warnings"] = link_validation_warnings
            session["link_warnings"] = link_validation_warnings
        result["session"] = session
    except Exception as exc:
        _attach_link_warnings(result, link_validation_warnings)
        result["error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
        }
        result["traceback"] = traceback.format_exc()
    finally:
        result["stdout"] = writer.getvalue()
        result["stdout_truncated"] = writer.truncated
        result["metrics"]["worker_duration_ms"] = (time.monotonic() - started) * 1000.0
        for name in reversed(opened):
            with contextlib.suppress(Exception):
                FreeCAD.closeDocument(name)
        if result_path:
            write_json_atomic(result_path, result)
    return 0 if result["status"] == "ok" else 1


def main() -> int:
    return run_job(job_path_from_argv(sys.argv))
