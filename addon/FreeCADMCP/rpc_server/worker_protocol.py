"""Versioned JSON protocol and resource limits for FreeCADCmd workers."""

from __future__ import annotations

import ast
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
MAX_CODE_BYTES = 1 * 1024 * 1024
MAX_STDOUT_BYTES = 1 * 1024 * 1024
MAX_MANIFEST_BYTES = 1 * 1024 * 1024
MAX_RESULT_BYTES = 8 * 1024 * 1024
MAX_ARTIFACT_BYTES = 256 * 1024 * 1024
MAX_ARTIFACTS_TOTAL_BYTES = 512 * 1024 * 1024
MAX_TEMP_ROOT_BYTES = 2 * 1024 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 120.0
MAX_TIMEOUT_SECONDS = 900.0


class ProtocolError(ValueError):
    pass


class UnsupportedWorkerGuiError(ProtocolError):
    pass


_SUBELEMENT_RE = re.compile(r"^(Face|Edge|Vertex)([1-9][0-9]*)$")


def _is_null_subobject(value: Any) -> bool:
    if value is None:
        return True
    is_null = getattr(value, "isNull", None)
    if callable(is_null):
        try:
            return bool(is_null())
        except Exception:
            return False
    return False


def _subelement_name_is_safe(name: str) -> bool:
    """Reject empty or path-like names; allow semantic identifiers such as H_Axis."""
    if not name or name in {".", ".."}:
        return False
    if any(ord(ch) < 32 for ch in name):
        return False
    if "/" in name or "\\" in name:
        return False
    if ".." in name:
        return False
    return True


def _resolve_via_get_subobject(target: Any, name: str) -> Any | None:
    getter = getattr(target, "getSubObject", None)
    if not callable(getter):
        return None
    try:
        resolved = getter(name)
    except Exception:
        return None
    if _is_null_subobject(resolved):
        return None
    return resolved


def _resolve_via_shape_element(shape: Any, name: str) -> Any | None:
    getter = getattr(shape, "getElement", None)
    if not callable(getter):
        return None
    try:
        resolved = getter(name)
    except Exception:
        return None
    if _is_null_subobject(resolved):
        return None
    return resolved


def validate_subelement_reference(target: Any, subelement: str) -> None:
    """Resolve a shape or semantic subelement and reject nonexistent references.

    Indexed ``FaceN``/``EdgeN``/``VertexN`` names are validated against shape
    collections. Other safe names (for example Sketcher ``H_Axis``) are resolved
    via ``target.getSubObject``, with ``Shape.getElement`` as a fallback.
    """
    name = str(subelement)
    owner = getattr(target, "Name", "<unknown>")
    shape = getattr(target, "Shape", None)
    match = _SUBELEMENT_RE.fullmatch(name)
    if match:
        if shape is None:
            raise ProtocolError(f"{owner}.{name} has no target shape")
        collection_name = {
            "Face": "Faces",
            "Edge": "Edges",
            "Vertex": "Vertexes",
        }[match.group(1)]
        collection = getattr(shape, collection_name, None)
        index = int(match.group(2))
        if collection is None or index > len(collection):
            raise ProtocolError(f"{owner}.{name} does not exist")
        return
    if not _subelement_name_is_safe(name):
        raise ProtocolError(f"{owner}.{name} does not exist")
    if _resolve_via_get_subobject(target, name) is not None:
        return
    if shape is not None and _resolve_via_shape_element(shape, name) is not None:
        return
    if shape is None and not callable(getattr(target, "getSubObject", None)):
        raise ProtocolError(f"{owner}.{name} has no target shape")
    raise ProtocolError(f"{owner}.{name} does not exist")


class CappedTextWriter:
    """Capture text without ever retaining more than the configured byte cap."""

    def __init__(self, limit: int = MAX_STDOUT_BYTES):
        self.limit = limit
        self._data = bytearray()
        self.truncated = False

    def write(self, value: str) -> int:
        encoded = str(value).encode("utf-8", errors="replace")
        remaining = max(0, self.limit - len(self._data))
        if remaining:
            self._data.extend(encoded[:remaining])
        if len(encoded) > remaining:
            self.truncated = True
        return len(value)

    def flush(self) -> None:
        return None

    def getvalue(self) -> str:
        return bytes(self._data).decode("utf-8", errors="replace")


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
    artifact_directory = job.get("artifact_directory")
    if not isinstance(artifact_directory, str) or not artifact_directory:
        raise ProtocolError("worker artifact_directory is required")


def write_json_atomic(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_RESULT_BYTES:
        raise ProtocolError("worker result JSON exceeds 8 MiB")
    fd, tmp_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
    except Exception:
        try:
            os.remove(tmp_name)
        except OSError:
            pass
        raise


def read_json_limited(path: str | Path, limit: int = MAX_RESULT_BYTES) -> dict[str, Any]:
    target = Path(path)
    size = target.stat().st_size
    if size > limit:
        raise ProtocolError(f"JSON file exceeds {limit} bytes")
    with target.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ProtocolError("JSON protocol payload must be an object")
    return value
