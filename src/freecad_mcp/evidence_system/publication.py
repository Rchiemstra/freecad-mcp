from __future__ import annotations
import os
from pathlib import Path
import tempfile
from .validation import ValidationResult


def fresh_output_gate(path: Path) -> ValidationResult:
    try:
        if not path.exists():
            return ValidationResult.ok()
        first = next(path.iterdir(), None)
    except OSError:
        return ValidationResult.fail("lifecycle", "OUTPUT_UNREADABLE", path.name, "/")
    if first is not None:
        return ValidationResult.fail("lifecycle", "OUTPUT_STALE", first.name, "/")
    return ValidationResult.ok()


def publish_once(path: Path, payload: bytes) -> ValidationResult:
    """Atomically publish bytes without ever replacing an existing artifact."""
    try:
        descriptor, temporary_name = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    except OSError:
        return ValidationResult.fail("lifecycle", "PUBLICATION_DIRECTORY_UNAVAILABLE", path.name, "/")
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            return ValidationResult.fail("lifecycle", "ARTIFACT_ALREADY_EXISTS", path.name, "/")
        except OSError:
            return ValidationResult.fail("lifecycle", "CREATE_ONLY_UNAVAILABLE", path.name, "/")
        return ValidationResult.ok()
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
