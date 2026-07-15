"""Production entry point executed inside one isolated FreeCADCmd process."""

from __future__ import annotations

import contextlib
import builtins
import os
import re
import sys
import time
import traceback
from pathlib import Path

import FreeCAD

try:
    from worker_protocol import (
        CappedTextWriter,
        MAX_ARTIFACT_BYTES,
        MAX_ARTIFACTS_TOTAL_BYTES,
        UnsupportedWorkerGuiError,
        read_json_limited,
        validate_subelement_reference,
        validate_job,
        write_json_atomic,
    )
except ImportError:  # direct package import in tests
    from .worker_protocol import (
        CappedTextWriter,
        MAX_ARTIFACT_BYTES,
        MAX_ARTIFACTS_TOTAL_BYTES,
        UnsupportedWorkerGuiError,
        read_json_limited,
        validate_subelement_reference,
        validate_job,
        write_json_atomic,
    )


def _job_path_from_argv(argv: list[str]) -> str:
    if "--pass" not in argv:
        raise ValueError("worker job must be provided after --pass")
    values = argv[argv.index("--pass") + 1 :]
    if len(values) != 1:
        raise ValueError("worker requires exactly one job JSON path after --pass")
    return values[0]


class ExternalLinkUnresolved(RuntimeError):
    pass


class ExternalSubelementUnresolved(RuntimeError):
    pass


class ArtifactLimitError(RuntimeError):
    pass


def _worker_builtins():
    """Reject GUI imports through the supported worker API (not a sandbox)."""
    namespace = dict(vars(builtins))
    original_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if str(name).split(".", 1)[0] == "FreeCADGui":
            raise UnsupportedWorkerGuiError("FreeCADGui is unsupported in worker jobs")
        return original_import(name, globals, locals, fromlist, level)

    namespace["__import__"] = guarded_import
    return namespace


class ArtifactEmitter:
    def __init__(self, directory: str, document):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.document = document
        self.artifacts = []
        self.total_bytes = 0

    def __call__(self, name, value, format="brep"):
        import Part

        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(name)).strip("._")
        if not safe_name:
            raise ValueError("artifact name contains no safe characters")
        artifact_format = str(format).lower()
        if artifact_format not in {"brep", "step"}:
            raise ValueError("artifact format must be 'brep' or 'step'")
        suffix = ".brep" if artifact_format == "brep" else ".step"
        path = (self.directory / f"{safe_name}{suffix}").resolve()
        if self.directory not in path.parents:
            raise ValueError("artifact path escaped its assigned directory")
        shape = getattr(value, "Shape", value)
        temporary = None
        try:
            if artifact_format == "brep":
                if not hasattr(shape, "exportBrep"):
                    raise TypeError("BREP artifacts require a Part.Shape or shaped object")
                shape.exportBrep(str(path))
            else:
                if hasattr(value, "Document") and hasattr(value, "Shape"):
                    objects = [value]
                else:
                    temporary = self.document.addObject("Part::Feature", "MCPWorkerArtifact")
                    temporary.Shape = shape
                    objects = [temporary]
                Part.export(objects, str(path))
            size = path.stat().st_size
            if size > MAX_ARTIFACT_BYTES:
                raise ArtifactLimitError("individual artifact exceeds 256 MiB")
            if self.total_bytes + size > MAX_ARTIFACTS_TOTAL_BYTES:
                raise ArtifactLimitError("job artifacts exceed 512 MiB total")
            self.total_bytes += size
            metadata = {
                "name": safe_name,
                "format": artifact_format,
                "path": str(path),
                "size_bytes": size,
            }
            self.artifacts.append(metadata)
            return metadata
        except Exception:
            try:
                path.unlink()
            except OSError:
                pass
            raise
        finally:
            if temporary is not None:
                try:
                    self.document.removeObject(temporary.Name)
                except Exception:
                    pass


def _reference_entries(value):
    if hasattr(value, "Document") and hasattr(value, "Name"):
        return [(value, [])]
    if isinstance(value, tuple) and value and hasattr(value[0], "Document"):
        subs = []
        for item in value[1:]:
            if isinstance(item, str):
                subs.append(item)
            elif isinstance(item, (list, tuple)):
                subs.extend(str(sub) for sub in item)
        return [(value[0], subs)]
    if isinstance(value, (list, tuple)):
        refs = []
        for item in value:
            refs.extend(_reference_entries(item))
        return refs
    return []


def _validate_expected_links(snapshot) -> None:
    missing_links = []
    missing_subelements = []
    for expected in snapshot.get("expected_links", []):
        owner_doc = FreeCAD.getDocument(expected["owner_document"])
        owner = owner_doc.getObject(expected["owner_object"]) if owner_doc else None
        if owner is None:
            missing_links.append(
                f"{expected['owner_document']}.{expected['owner_object']}.{expected['property']}"
            )
            continue
        try:
            refs = _reference_entries(getattr(owner, expected["property"]))
        except Exception:
            refs = []
        matched = False
        identity_matched = False
        for target, subelements in refs:
            if (
                target.Document.Name == expected["target_document"]
                and target.Name == expected["target_object"]
                and list(subelements) == list(expected.get("subelements", []))
            ):
                identity_matched = True
                try:
                    for subelement in subelements:
                        validate_subelement_reference(target, subelement)
                except Exception as exc:
                    missing_subelements.append(str(exc))
                    continue
                matched = True
                break
        if not matched and not identity_matched:
            missing_links.append(
                f"{expected['owner_document']}.{expected['owner_object']}.{expected['property']}"
            )
    if missing_links:
        raise ExternalLinkUnresolved(
            "Snapshot links did not resolve: " + ", ".join(sorted(set(missing_links)))
        )
    if missing_subelements:
        raise ExternalSubelementUnresolved(
            "Snapshot subelements did not resolve: "
            + ", ".join(sorted(set(missing_subelements)))
        )


def run_job(job_path: str) -> int:
    job = read_json_limited(job_path)
    result_path = job.get("result_path")
    started = time.monotonic()
    writer = CappedTextWriter()
    opened = []
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
    try:
        validate_job(job)
        if job["kind"] == "probe":
            result["status"] = "ok"
            result["session"] = {"freecad_version": list(FreeCAD.Version())}
            return 0
        snapshot = job["snapshot"]
        for entry in snapshot["documents"]:
            doc = FreeCAD.openDocument(entry["load_path"])
            opened.append(doc.Name)
        primary_name = snapshot["primary_document"]
        primary = FreeCAD.getDocument(primary_name)
        if primary is None:
            raise RuntimeError(f"Primary snapshot did not open as {primary_name!r}")
        FreeCAD.setActiveDocument(primary.Name)
        if snapshot.get("expected_links"):
            for doc in FreeCAD.listDocuments().values():
                doc.recompute()
            _validate_expected_links(snapshot)
        options = job.get("options") or {}
        recompute = options.get("recompute", "none")
        if recompute == "all":
            for doc in FreeCAD.listDocuments().values():
                doc.recompute()
        elif recompute == "target":
            primary.recompute()

        emitter = ArtifactEmitter(job["artifact_directory"], primary)
        namespace = {
            "__builtins__": _worker_builtins(),
            "__name__": "__mcp_worker_job__",
            "FreeCAD": FreeCAD,
            "App": FreeCAD,
            "emit_artifact": emitter,
        }
        with contextlib.redirect_stdout(writer):
            exec(job["code"], namespace)
        result["status"] = "ok"
        result["artifacts"] = emitter.artifacts
        result["session"] = {
            "active_document_after": FreeCAD.ActiveDocument.Name if FreeCAD.ActiveDocument else None,
            "documents": sorted(FreeCAD.listDocuments().keys()),
            "worker_read_only_snapshot": True,
        }
    except Exception as exc:
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
            try:
                FreeCAD.closeDocument(name)
            except Exception:
                pass
        if result_path:
            write_json_atomic(result_path, result)
    return 0 if result["status"] == "ok" else 1


def main() -> int:
    return run_job(_job_path_from_argv(sys.argv))


# FreeCAD loads .py command-line inputs as modules. The --pass marker makes this
# invocation distinguishable from imports performed by tests or other modules.
if "--pass" in sys.argv:
    _exit_code = main()
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    finally:
        os._exit(_exit_code)
