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
        validate_snapshot_manifest,
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
        validate_snapshot_manifest,
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


def _ignored_links_for_property(
    snapshot: dict,
    key: tuple[str, str, str],
) -> dict[int, dict]:
    ignored: dict[int, dict] = {}
    for entry in snapshot.get("ignored_links") or []:
        entry_key = (
            entry["owner_document"],
            entry["owner_object"],
            entry["property"],
        )
        if entry_key != key:
            continue
        index = int(entry["reference_index"])
        if index in ignored:
            raise ExternalLinkUnresolved(
                f"Snapshot links did not resolve: {key[0]}.{key[1]}.{key[2]}"
            )
        ignored[index] = entry
    return ignored


def _live_subelements_match_warn_policy(
    live_subs,
    kept_subs: list[str],
    ignored_subs: list[str],
) -> bool:
    live = [str(item) for item in live_subs]
    kept = [str(item) for item in kept_subs]
    ignored = [str(item) for item in ignored_subs]
    if len(live) != len(kept) + len(ignored):
        return False
    if [item for item in live if item in set(kept)] != kept:
        return False
    if [item for item in live if item in set(ignored)] != ignored:
        return False
    return set(live) == set(kept) | set(ignored)


def _current_kept_subelements_post_recompute(
    live_subs,
    ignored_subs: list[str],
) -> list[str] | None:
    """Live subs with warn-policy ignored subs removed (multiset, first occurrence)."""
    remaining = [str(item) for item in live_subs]
    for ign in ignored_subs:
        if ign not in remaining:
            return None
        remaining.remove(ign)
    return remaining


def _property_type_for_key(
    snapshot: dict,
    key: tuple[str, str, str],
) -> str:
    for source in (snapshot.get("expected_links") or [], snapshot.get("ignored_links") or []):
        for entry in source:
            if _property_group_key(entry) == key:
                return str(entry.get("property_type") or "")
    return ""


def _is_single_linksub_property(property_type: str) -> bool:
    return bool(property_type) and "LinkSub" in property_type and "LinkSubList" not in property_type


def _normalize_reference_entries_for_property(
    refs: list[tuple],
    *,
    property_type: str,
    label: str,
) -> list[tuple]:
    """Collapse accidental per-subelement splits on single-target LinkSub properties."""
    if not refs or not _is_single_linksub_property(property_type) or len(refs) == 1:
        return refs
    target_doc = refs[0][0].Document.Name
    target_name = refs[0][0].Name
    subs: list[str] = []
    for target, subelements in refs:
        if target.Document.Name != target_doc or target.Name != target_name:
            raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")
        subs.extend(str(item) for item in subelements)
    return [(refs[0][0], subs)]


def _expected_rows_by_reference_index(rows: list[dict]) -> dict[int, dict]:
    indexed: dict[int, dict] = {}
    for offset, row in enumerate(rows):
        index = int(row["reference_index"]) if "reference_index" in row else offset
        if index in indexed:
            raise ExternalLinkUnresolved(
                f"Snapshot links did not resolve: duplicate reference_index {index}"
            )
        indexed[index] = row
    return indexed


def _validate_ignored_reference(
    ignored: dict,
    target,
    subelements,
    label: str,
) -> None:
    if (
        target.Document.Name != ignored["target_document"]
        or target.Name != ignored["target_object"]
    ):
        raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")
    ignored_subs = [str(item) for item in ignored.get("subelements", [])]
    if not ignored_subs:
        raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")
    if not _live_subelements_match_warn_policy(subelements, [], ignored_subs):
        raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")


def _validate_property_group_pre_recompute(
    expected_rows: list[dict],
    snapshot: dict,
    *,
    property_key: tuple[str, str, str],
) -> list[dict]:
    """Phase 1 for one property: exact-order reopen fidelity with warn-policy exemptions."""
    key = property_key
    refs, label = _read_property_reference_entries(key[0], key[1], key[2])
    property_type = _property_type_for_key(snapshot, key)
    refs = _normalize_reference_entries_for_property(
        refs, property_type=property_type, label=label
    )
    ignored_by_index = _ignored_links_for_property(snapshot, key)
    expected_by_ref = _expected_rows_by_reference_index(expected_rows)
    anchors: list[dict] = []
    for ref_index, (target, subelements) in enumerate(refs):
        ignored = ignored_by_index.get(ref_index)
        expected = expected_by_ref.pop(ref_index, None)
        if ignored is not None and expected is not None:
            kept_subs = [str(item) for item in expected.get("subelements", [])]
            ignored_subs = [str(item) for item in ignored.get("subelements", [])]
            if (
                target.Document.Name != expected["target_document"]
                or target.Name != expected["target_object"]
                or target.Document.Name != ignored["target_document"]
                or target.Name != ignored["target_object"]
                or not _live_subelements_match_warn_policy(
                    subelements, kept_subs, ignored_subs
                )
            ):
                raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")
            anchors.append({"expected": expected, "ref_index": ref_index})
            continue
        if ignored is not None:
            _validate_ignored_reference(ignored, target, subelements, label)
            continue
        if expected is None:
            raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")
        if _reference_identity(target, subelements) != _manifest_identity(expected):
            raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")
        anchors.append({"expected": expected, "ref_index": ref_index})
    if expected_by_ref:
        raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")
    return anchors


def _recompute_snapshot_documents() -> None:
    for doc in FreeCAD.listDocuments().values():
        doc.recompute()


def _property_keys_in_snapshot(snapshot: dict) -> list[tuple[str, str, str]]:
    order: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for entry in list(snapshot.get("expected_links") or []) + list(
        snapshot.get("ignored_links") or []
    ):
        key = _property_group_key(entry)
        if key in seen:
            continue
        seen.add(key)
        order.append(key)
    return order


def _validate_expected_links_pre_recompute(snapshot) -> list[dict]:
    """Phase 1: per-property exact-order reopen fidelity before any document recompute."""
    validate_snapshot_manifest(snapshot)
    anchors: list[dict] = []
    expected_map = dict(_group_expected_link_entries(snapshot.get("expected_links", [])))
    for key in _property_keys_in_snapshot(snapshot):
        anchors.extend(
            _validate_property_group_pre_recompute(
                expected_map.get(key, []), snapshot, property_key=key
            )
        )
    return anchors


def _validate_property_group_post_recompute(
    anchors_for_property: list[dict],
    snapshot: dict,
    *,
    property_key: tuple[str, str, str],
) -> list[str]:
    """Phase 2 for one property: same entry count/order, target identity, subelement resolution.

    Post-recompute topological renaming is accepted only as same-index subelement name
    changes on the same target object that still pass ``validate_subelement_reference``.
    This does not prove persistent-topology equivalence for arbitrary valid faces.
    LinkSubList entry reordering is rejected because indices must still match the manifest.
    """
    key = property_key
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
    property_type = _property_type_for_key(snapshot, key)
    refs = _normalize_reference_entries_for_property(
        refs, property_type=property_type, label=label
    )
    ignored_by_index = _ignored_links_for_property(snapshot, key)
    expected_by_ref = {
        int(anchor["ref_index"]): anchor["expected"] for anchor in anchors_for_property
    }
    warnings: list[str] = []
    missing_subelements: list[str] = []
    for ref_index, (target, subelements) in enumerate(refs):
        ignored = ignored_by_index.get(ref_index)
        expected = expected_by_ref.pop(ref_index, None)
        if ignored is not None and expected is not None:
            kept_subs = [str(item) for item in expected.get("subelements", [])]
            ignored_subs = [str(item) for item in ignored.get("subelements", [])]
            if (
                target.Document.Name != expected["target_document"]
                or target.Name != expected["target_object"]
                or target.Document.Name != ignored["target_document"]
                or target.Name != ignored["target_object"]
            ):
                raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")
            current_kept_subs = _current_kept_subelements_post_recompute(
                subelements, ignored_subs
            )
            if current_kept_subs is None:
                raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")
            entry_label = _expected_link_label(expected)
            for subelement in current_kept_subs:
                try:
                    validate_subelement_reference(target, subelement)
                except Exception as exc:
                    missing_subelements.append(str(exc))
            if len(current_kept_subs) != len(kept_subs):
                raise ExternalLinkUnresolved(
                    f"Snapshot links did not resolve: {entry_label}"
                )
            if current_kept_subs != kept_subs:
                remap = ", ".join(
                    f"{before} -> {after}"
                    for before, after in zip(kept_subs, current_kept_subs)
                )
                warnings.append(f"subelement_remapped:{entry_label}: {remap}")
            continue
        if ignored is not None:
            _validate_ignored_reference(ignored, target, subelements, label)
            continue
        if expected is None:
            raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")
        entry_label = _expected_link_label(expected)
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
    if expected_by_ref:
        raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")
    if missing_subelements:
        raise ExternalSubelementUnresolved(
            "Snapshot subelements did not resolve: "
            + ", ".join(sorted(set(missing_subelements)))
        )
    return warnings


def _validate_expected_links_post_recompute(anchors: list[dict], snapshot: dict) -> list[str]:
    warnings: list[str] = []
    anchors_by_property: dict[tuple[str, str, str], list[dict]] = {}
    for anchor in anchors:
        key = _property_group_key(anchor["expected"])
        anchors_by_property.setdefault(key, []).append(anchor)
    for key in _property_keys_in_snapshot(snapshot):
        property_anchors = anchors_by_property.get(key, [])
        if not property_anchors and not _ignored_links_for_property(snapshot, key):
            continue
        warnings.extend(
            _validate_property_group_post_recompute(
                property_anchors, snapshot, property_key=key
            )
        )
    return warnings


def _apply_snapshot_test_hooks(snapshot: dict, *, stage: str) -> None:
    if os.environ.get("FREECAD_TEST") != "1":
        return
    hooks = snapshot.get("test_hooks") or {}
    if stage == "after_recompute":
        hook = hooks.get("after_recompute_remap")
        if not hook:
            return
        doc = FreeCAD.getDocument(hook["owner_document"])
        owner = doc.getObject(hook["owner_object"])
        target = doc.getObject(hook["target_object"])
        subs = [str(item) for item in hook.get("subelements", [])]
        setattr(owner, hook["property"], (target, subs))


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
        if snapshot.get("expected_links") or snapshot.get("ignored_links"):
            link_anchors = _validate_expected_links_pre_recompute(snapshot)
            _recompute_snapshot_documents()
            _apply_snapshot_test_hooks(snapshot, stage="after_recompute")
            link_validation_warnings = _validate_expected_links_post_recompute(
                link_anchors, snapshot
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
