"""Worker job schema validation and GUI usage rejection."""

from __future__ import annotations

import ast
import json
from typing import Any

from ..worker_protocol_types.protocol_error import ProtocolError
from ..worker_protocol_types.unsupported_worker_gui_error import UnsupportedWorkerGuiError
from .constants import (
    DEFAULT_TIMEOUT_SECONDS,
    MAX_CODE_BYTES,
    MAX_MANIFEST_BYTES,
    MAX_TIMEOUT_SECONDS,
    SCHEMA_VERSION,
)


def clamp_timeout(value: Any) -> float:
    if value is None:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        timeout = float(value)
    except (TypeError, ValueError) as exc:
        raise ProtocolError("timeout_seconds must be a number") from exc
    if timeout < 1 or timeout > MAX_TIMEOUT_SECONDS:
        raise ProtocolError(
            f"timeout_seconds must be between 1 and {MAX_TIMEOUT_SECONDS:g}"
        )
    return timeout


def reject_detectable_gui_usage(code: str) -> None:
    """Reject direct GUI imports/references; this is not a security sandbox."""
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError:
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [item.name for item in node.names]
            if any(name == "FreeCADGui" or name.startswith("FreeCADGui.") for name in names):
                raise UnsupportedWorkerGuiError("FreeCADGui is unsupported in worker jobs")
        elif isinstance(node, ast.ImportFrom):
            if node.module and (
                node.module == "FreeCADGui" or node.module.startswith("FreeCADGui.")
            ):
                raise UnsupportedWorkerGuiError("FreeCADGui is unsupported in worker jobs")
        elif isinstance(node, ast.Name) and node.id in {"FreeCADGui", "Gui"}:
            raise UnsupportedWorkerGuiError("FreeCADGui is unsupported in worker jobs")
        elif isinstance(node, ast.Attribute) and node.attr == "Gui":
            raise UnsupportedWorkerGuiError("FreeCAD GUI access is unsupported in worker jobs")


_IGNORED_LINK_REQUIRED_KEYS = (
    "owner_document",
    "owner_object",
    "property",
    "reference_index",
    "target_document",
    "target_object",
    "subelements",
)


def _validate_ignored_link_entry(
    entry: Any,
    seen_ignored: set[tuple[str, str, str, int]],
) -> None:
    if not isinstance(entry, dict):
        raise ProtocolError("ignored_links entries must be objects")
    for key in _IGNORED_LINK_REQUIRED_KEYS:
        if key not in entry:
            raise ProtocolError(f"ignored_links entry missing {key!r}")
    if not isinstance(entry["reference_index"], int) or entry["reference_index"] < 0:
        raise ProtocolError("ignored_links reference_index must be a non-negative int")
    subelements = entry["subelements"]
    if not isinstance(subelements, list) or not subelements:
        raise ProtocolError("ignored_links subelements must be a non-empty list")
    if not all(isinstance(item, str) and item for item in subelements):
        raise ProtocolError("ignored_links subelements must be non-empty strings")
    dedupe_key = (
        str(entry["owner_document"]),
        str(entry["owner_object"]),
        str(entry["property"]),
        int(entry["reference_index"]),
    )
    if dedupe_key in seen_ignored:
        raise ProtocolError("ignored_links contains duplicate reference_index")
    seen_ignored.add(dedupe_key)


def validate_snapshot_manifest(snapshot: dict[str, Any]) -> None:
    """Validate snapshot link metadata carried into isolated workers."""
    if not isinstance(snapshot, dict):
        raise ProtocolError("worker snapshot manifest must be an object")
    link_policy = snapshot.get("link_policy", "strict")
    if link_policy not in {"strict", "warn"}:
        raise ProtocolError(f"unsupported link_policy: {link_policy!r}")
    ignored_links = snapshot.get("ignored_links", [])
    if ignored_links is None:
        ignored_links = []
    if not isinstance(ignored_links, list):
        raise ProtocolError("ignored_links must be a list")
    if link_policy == "strict" and ignored_links:
        raise ProtocolError("ignored_links requires link_policy warn")
    seen_ignored: set[tuple[str, str, str, int]] = set()
    for entry in ignored_links:
        _validate_ignored_link_entry(entry, seen_ignored)


def _validate_execute_code_job(job: dict[str, Any]) -> None:
    code = job.get("code")
    if not isinstance(code, str):
        raise ProtocolError("worker code must be a string")
    if len(code.encode("utf-8")) > MAX_CODE_BYTES:
        raise ProtocolError("worker code exceeds 1 MiB")
    reject_detectable_gui_usage(code)
    result_path = job.get("result_path")
    if not isinstance(result_path, str) or not result_path:
        raise ProtocolError("worker result_path is required")
    clamp_timeout((job.get("options") or {}).get("timeout_seconds"))
    manifest = job.get("snapshot")
    if not isinstance(manifest, dict) or not manifest.get("documents"):
        raise ProtocolError("worker snapshot manifest is required")
    encoded_manifest = json.dumps(manifest).encode("utf-8")
    if len(encoded_manifest) > MAX_MANIFEST_BYTES:
        raise ProtocolError("worker snapshot manifest exceeds 1 MiB")
    validate_snapshot_manifest(manifest)
    artifact_directory = job.get("artifact_directory")
    if not isinstance(artifact_directory, str) or not artifact_directory:
        raise ProtocolError("worker artifact_directory is required")


def validate_job(job: dict[str, Any]) -> None:
    if job.get("schema_version") != SCHEMA_VERSION:
        raise ProtocolError("unsupported worker job schema")
    if job.get("kind") not in {"execute_code", "probe"}:
        raise ProtocolError("unsupported worker job kind")
    if not isinstance(job.get("job_id"), str) or not job["job_id"]:
        raise ProtocolError("worker job_id is required")
    if job.get("kind") == "probe":
        result_path = job.get("result_path")
        if not isinstance(result_path, str) or not result_path:
            raise ProtocolError("worker result_path is required")
        return
    _validate_execute_code_job(job)
