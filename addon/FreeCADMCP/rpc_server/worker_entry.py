"""Production entry point executed inside one isolated FreeCADCmd process."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import FreeCAD


def _insert_sys_path(path: Path) -> None:
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)


def _bootstrap_worker_import_paths() -> None:
    if __package__ not in {None, ""}:
        return
    rpc_server = Path(__file__).resolve().parent
    if not (rpc_server / "worker_entry_ops").is_dir():
        for entry in sys.path:
            candidate = Path(entry)
            if (candidate / "worker_entry_ops").is_dir():
                rpc_server = candidate
                break
    freecad_mcp = rpc_server.parent
    for candidate in (
        rpc_server.parent.parent.parent,
        rpc_server.parent.parent,
        rpc_server.parent,
    ):
        if (candidate / "addon" / "FreeCADMCP").is_dir():
            _insert_sys_path(candidate)
            return
        if candidate.name == "FreeCADMCP" and (candidate / "rpc_server").is_dir():
            _insert_sys_path(candidate.parent)
            return
    _insert_sys_path(rpc_server)
    _insert_sys_path(freecad_mcp.parent)


_bootstrap_worker_import_paths()

try:
    from .worker_entry_ops.artifact_emitter import ArtifactEmitter
    from .worker_entry_ops.link_validation_helpers import (
        _group_expected_link_entries,
        _manifest_identity,
        _read_property_reference_entries,
        _recompute_snapshot_documents,
    )
    from .worker_entry_ops.link_validation_post import (
        _validate_expected_links_post_recompute,
    )
    from .worker_entry_ops.link_validation_pre import (
        _validate_expected_links_pre_recompute,
        _validate_property_group_pre_recompute,
    )
    from .worker_entry_ops.run_job import main, run_job
    from .worker_entry_types.artifact_limit_error import ArtifactLimitError
    from .worker_entry_types.external_link_unresolved import ExternalLinkUnresolved
    from .worker_entry_types.external_subelement_unresolved import (
        ExternalSubelementUnresolved,
    )
except ImportError:  # FreeCADCmd script execution without a package context
    try:
        from worker_entry_ops.artifact_emitter import ArtifactEmitter
        from worker_entry_ops.link_validation_helpers import (
            _group_expected_link_entries,
            _manifest_identity,
            _read_property_reference_entries,
            _recompute_snapshot_documents,
        )
        from worker_entry_ops.link_validation_post import (
            _validate_expected_links_post_recompute,
        )
        from worker_entry_ops.link_validation_pre import (
            _validate_expected_links_pre_recompute,
            _validate_property_group_pre_recompute,
        )
        from worker_entry_ops.run_job import main, run_job
        from worker_entry_types.artifact_limit_error import ArtifactLimitError
        from worker_entry_types.external_link_unresolved import ExternalLinkUnresolved
        from worker_entry_types.external_subelement_unresolved import (
            ExternalSubelementUnresolved,
        )
    except ImportError:
        try:
            from addon.FreeCADMCP.rpc_server.worker_entry_ops.artifact_emitter import (
                ArtifactEmitter,
            )
            from addon.FreeCADMCP.rpc_server.worker_entry_ops.link_validation_helpers import (
                _group_expected_link_entries,
                _manifest_identity,
                _read_property_reference_entries,
                _recompute_snapshot_documents,
            )
            from addon.FreeCADMCP.rpc_server.worker_entry_ops.link_validation_post import (
                _validate_expected_links_post_recompute,
            )
            from addon.FreeCADMCP.rpc_server.worker_entry_ops.link_validation_pre import (
                _validate_expected_links_pre_recompute,
                _validate_property_group_pre_recompute,
            )
            from addon.FreeCADMCP.rpc_server.worker_entry_ops.run_job import main, run_job
            from addon.FreeCADMCP.rpc_server.worker_entry_types.artifact_limit_error import (
                ArtifactLimitError,
            )
            from addon.FreeCADMCP.rpc_server.worker_entry_types.external_link_unresolved import (
                ExternalLinkUnresolved,
            )
            from addon.FreeCADMCP.rpc_server.worker_entry_types.external_subelement_unresolved import (
                ExternalSubelementUnresolved,
            )
        except ImportError:
            from FreeCADMCP.rpc_server.worker_entry_ops.artifact_emitter import ArtifactEmitter
            from FreeCADMCP.rpc_server.worker_entry_ops.link_validation_helpers import (
                _group_expected_link_entries,
                _manifest_identity,
                _read_property_reference_entries,
                _recompute_snapshot_documents,
            )
            from FreeCADMCP.rpc_server.worker_entry_ops.link_validation_post import (
                _validate_expected_links_post_recompute,
            )
            from FreeCADMCP.rpc_server.worker_entry_ops.link_validation_pre import (
                _validate_expected_links_pre_recompute,
                _validate_property_group_pre_recompute,
            )
            from FreeCADMCP.rpc_server.worker_entry_ops.run_job import main, run_job
            from FreeCADMCP.rpc_server.worker_entry_types.artifact_limit_error import (
                ArtifactLimitError,
            )
            from FreeCADMCP.rpc_server.worker_entry_types.external_link_unresolved import (
                ExternalLinkUnresolved,
            )
            from FreeCADMCP.rpc_server.worker_entry_types.external_subelement_unresolved import (
                ExternalSubelementUnresolved,
            )

__all__ = [
    "ArtifactEmitter",
    "ArtifactLimitError",
    "ExternalLinkUnresolved",
    "ExternalSubelementUnresolved",
    "FreeCAD",
    "_group_expected_link_entries",
    "_manifest_identity",
    "_read_property_reference_entries",
    "_recompute_snapshot_documents",
    "_validate_expected_links_post_recompute",
    "_validate_expected_links_pre_recompute",
    "_validate_property_group_pre_recompute",
    "main",
    "run_job",
]

# FreeCAD loads .py command-line inputs as modules. The --pass marker makes this
# invocation distinguishable from imports performed by tests or other modules.
if "--pass" in sys.argv:
    _exit_code = main()
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    finally:
        os._exit(_exit_code)
