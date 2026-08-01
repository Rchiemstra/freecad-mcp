"""Versioned JSON protocol and resource limits for FreeCADCmd workers."""

from __future__ import annotations

# §3.3 compatibility shims — moved symbols keep their legacy import path.
from .worker_protocol_ops.constants import (
    DEFAULT_TIMEOUT_SECONDS,
    MAX_ARTIFACT_BYTES,
    MAX_ARTIFACTS_TOTAL_BYTES,
    MAX_CODE_BYTES,
    MAX_MANIFEST_BYTES,
    MAX_RESULT_BYTES,
    MAX_STDOUT_BYTES,
    MAX_TEMP_ROOT_BYTES,
    MAX_TIMEOUT_SECONDS,
    SCHEMA_VERSION,
)
from .worker_protocol_ops.job_validation import (
    clamp_timeout,
    reject_detectable_gui_usage,
    validate_job,
    validate_snapshot_manifest,
)
from .worker_protocol_ops.json_io import read_json_limited, write_json_atomic
from .worker_protocol_ops.subelement_validation import validate_subelement_reference
from .worker_protocol_types.capped_text_writer import CappedTextWriter
from .worker_protocol_types.protocol_error import ProtocolError
from .worker_protocol_types.unsupported_worker_gui_error import (
    UnsupportedWorkerGuiError,
)

__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "MAX_ARTIFACTS_TOTAL_BYTES",
    "MAX_ARTIFACT_BYTES",
    "MAX_CODE_BYTES",
    "MAX_MANIFEST_BYTES",
    "MAX_RESULT_BYTES",
    "MAX_STDOUT_BYTES",
    "MAX_TEMP_ROOT_BYTES",
    "MAX_TIMEOUT_SECONDS",
    "SCHEMA_VERSION",
    "CappedTextWriter",
    "ProtocolError",
    "UnsupportedWorkerGuiError",
    "clamp_timeout",
    "read_json_limited",
    "reject_detectable_gui_usage",
    "validate_job",
    "validate_snapshot_manifest",
    "validate_subelement_reference",
    "write_json_atomic",
]
