"""Emit bounded BREP/STEP artifacts from worker jobs."""

from __future__ import annotations

import contextlib
import re
from pathlib import Path

from ..worker_entry_types.artifact_limit_error import ArtifactLimitError
from ..worker_protocol_ops.constants import MAX_ARTIFACT_BYTES, MAX_ARTIFACTS_TOTAL_BYTES


def _write_artifact_shape(path, shape, artifact_format: str, value, document):
    import Part

    if artifact_format == "brep":
        if not hasattr(shape, "exportBrep"):
            raise TypeError("BREP artifacts require a Part.Shape or shaped object")
        shape.exportBrep(str(path))
        return None
    if hasattr(value, "Document") and hasattr(value, "Shape"):
        Part.export([value], str(path))
        return None
    temporary = document.addObject("Part::Feature", "MCPWorkerArtifact")
    temporary.Shape = shape
    Part.export([temporary], str(path))
    return temporary


class ArtifactEmitter:
    def __init__(self, directory: str, document):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.document = document
        self.artifacts = []
        self.total_bytes = 0

    def __call__(self, name, value, format="brep"):
        metadata = self._export_artifact(name, value, format=format)
        return metadata

    def _export_artifact(self, name, value, *, format: str):

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
            temporary = _write_artifact_shape(path, shape, artifact_format, value, self.document)
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
            with contextlib.suppress(OSError):
                path.unlink()
            raise
        finally:
            if temporary is not None:
                with contextlib.suppress(Exception):
                    self.document.removeObject(temporary.Name)
