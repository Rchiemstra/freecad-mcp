"""Subject ownership mapping for register modules."""

from __future__ import annotations

_SUBJECT_PREFIXES: tuple[tuple[str, str], ...] = (
    ("tools_runtime", "runtime"),
    ("tools_lease", "lease"),
    ("tools_core", "core"),
    ("tools_worker", "worker"),
    ("tools_gui", "gui"),
    ("tools_diagnostics", "diagnostics"),
    ("tools_sketch", "sketch"),
    ("tools_features", "features"),
    ("tools_document_history", "document_history"),
    ("tools_parametric", "parametric"),
    ("tools_gear", "gear"),
    ("tools_measure", "measure"),
    ("tools_transform", "transform"),
    ("tools_io", "io"),
    ("tools_assembly", "assembly"),
    ("tools_partdesign", "partdesign"),
    ("tools_advanced", "advanced"),
)


def subject_for_register_module(module_name: str) -> str:
    for prefix, subject in _SUBJECT_PREFIXES:
        if module_name.startswith(prefix):
            return subject
    raise ValueError(f"no capability subject for register module {module_name!r}")


__all__ = ["subject_for_register_module"]
