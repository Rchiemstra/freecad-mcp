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


def _expected_link_label(expected: dict) -> str:
    return (
        f"{expected['owner_document']}.{expected['owner_object']}.{expected['property']}"
    )


def _property_group_key(expected: dict) -> tuple[str, str, str]:
    return (
        expected["owner_document"],
        expected["owner_object"],
        expected["property"],
    )


def _manifest_identity(expected: dict) -> tuple[str, str, tuple[str, ...]]:
    return (
        expected["target_document"],
        expected["target_object"],
        tuple(str(item) for item in expected.get("subelements", [])),
    )


def _reference_identity(target, subelements) -> tuple[str, str, tuple[str, ...]]:
    return (
        target.Document.Name,
        target.Name,
        tuple(str(item) for item in subelements),
    )


def _group_expected_link_entries(
    entries: list[dict],
) -> list[tuple[tuple[str, str, str], list[dict]]]:
    """Group manifest rows by owner property while preserving manifest order."""
    groups: dict[tuple[str, str, str], list[dict]] = {}
    order: list[tuple[str, str, str]] = []
    for entry in entries:
        key = _property_group_key(entry)
        if key not in groups:
            order.append(key)
            groups[key] = []
        groups[key].append(entry)
    return [(key, groups[key]) for key in order]


def _read_property_reference_entries(
    owner_document: str,
    owner_object: str,
    property_name: str,
) -> tuple[list[tuple], str]:
    """Return parsed reference entries for one owner property or raise via label."""
    label = f"{owner_document}.{owner_object}.{property_name}"
    try:
        owner_doc = FreeCAD.getDocument(owner_document)
    except Exception:
        owner_doc = None
    if owner_doc is None:
        raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")
    owner = owner_doc.getObject(owner_object)
    if owner is None:
        raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")
    properties = getattr(owner, "PropertiesList", None)
    if not properties or property_name not in properties:
        raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")
    try:
        return _reference_entries(getattr(owner, property_name)), label
    except Exception:
        raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")


def _validate_property_group_pre_recompute(
    expected_rows: list[dict],
) -> list[dict]:
    """Phase 1 for one property: exact-order reopen fidelity of all reference entries."""
    if not expected_rows:
        return []
    key = _property_group_key(expected_rows[0])
    refs, label = _read_property_reference_entries(key[0], key[1], key[2])
    expected_identities = [_manifest_identity(row) for row in expected_rows]
    current_identities = [_reference_identity(target, subs) for target, subs in refs]
    if expected_identities != current_identities:
        raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")
    return [
        {"expected": expected, "ref_index": index}
        for index, expected in enumerate(expected_rows)
    ]


def _recompute_snapshot_documents() -> None:
    for doc in FreeCAD.listDocuments().values():
        doc.recompute()


def _validate_expected_links_pre_recompute(snapshot) -> list[dict]:
    """Phase 1: per-property exact-order reopen fidelity before any document recompute."""
    anchors: list[dict] = []
    for _key, expected_rows in _group_expected_link_entries(
        snapshot.get("expected_links", [])
    ):
        anchors.extend(_validate_property_group_pre_recompute(expected_rows))
    return anchors


def _validate_property_group_post_recompute(
    expected_rows: list[dict],
) -> list[str]:
    """Phase 2 for one property: same entry count/order, target identity, subelement resolution.

    Post-recompute topological renaming is accepted only as same-index subelement name
    changes on the same target object that still pass ``validate_subelement_reference``.
    This does not prove persistent-topology equivalence for arbitrary valid faces.
    LinkSubList entry reordering is rejected because indices must still match the manifest.
    """
    if not expected_rows:
        return []
    key = _property_group_key(expected_rows[0])
    label = f"{key[0]}.{key[1]}.{key[2]}"
    try:
        owner_doc = FreeCAD.getDocument(key[0])
    except Exception:
        owner_doc = None
    if owner_doc is None:
        raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")
    owner = owner_doc.getObject(key[1])
    if owner is None:
        raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")
    properties = getattr(owner, "PropertiesList", None)
    if not properties or key[2] not in properties:
        raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")
    try:
        refs = _reference_entries(getattr(owner, key[2]))
    except Exception:
        raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")
    if len(refs) != len(expected_rows):
        raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")
    warnings: list[str] = []
    missing_subelements: list[str] = []
    for ref_index, expected in enumerate(expected_rows):
        entry_label = _expected_link_label(expected)
        target, subelements = refs[ref_index]
        if (
            target.Document.Name != expected["target_document"]
            or target.Name != expected["target_object"]
        ):
            raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")
        expected_subs = [str(item) for item in expected.get("subelements", [])]
        current_subs = [str(item) for item in subelements]
        entry_subelement_errors: list[str] = []
        for subelement in current_subs:
            try:
                validate_subelement_reference(target, subelement)
            except Exception as exc:
                entry_subelement_errors.append(str(exc))
        if entry_subelement_errors:
            missing_subelements.extend(entry_subelement_errors)
            continue
        if len(current_subs) != len(expected_subs):
            raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {entry_label}")
        if current_subs != expected_subs:
            remap = ", ".join(
                f"{before} -> {after}"
                for before, after in zip(expected_subs, current_subs)
            )
            warnings.append(f"subelement_remapped:{entry_label}: {remap}")
    if missing_subelements:
        raise ExternalSubelementUnresolved(
            "Snapshot subelements did not resolve: "
            + ", ".join(sorted(set(missing_subelements)))
        )
    return warnings


def _validate_expected_links_post_recompute(anchors: list[dict]) -> list[str]:
    warnings: list[str] = []
    for _key, expected_rows in _group_expected_link_entries(
        [anchor["expected"] for anchor in anchors]
    ):
        warnings.extend(_validate_property_group_post_recompute(expected_rows))
    return warnings


def _attach_link_warnings(result: dict, link_validation_warnings: list[str]) -> None:
    if not link_validation_warnings:
        return
    result["link_warnings"] = list(link_validation_warnings)
    session = dict(result.get("session") or {})
    session["link_warnings"] = list(link_validation_warnings)
    result["session"] = session


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
    link_validation_warnings: list[str] = []
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
            link_anchors = _validate_expected_links_pre_recompute(snapshot)
            _recompute_snapshot_documents()
            link_validation_warnings = _validate_expected_links_post_recompute(
                link_anchors
            )
            _attach_link_warnings(result, link_validation_warnings)
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
        session = {
            "active_document_after": FreeCAD.ActiveDocument.Name if FreeCAD.ActiveDocument else None,
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
