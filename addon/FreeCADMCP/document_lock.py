"""Per-document renewable write lease for MCP agents.

Pure/unit-testable core: lease registry, atomic sidecar lock files, staleness
checks, and Save As / first-save key migration. FreeCAD and Qt are imported
lazily so the module loads under the stubbed unit harness.

When ``enable_document_lock`` is false (default), nothing is registered, no
sidecars are written, and callers should treat this module as inert.
"""

from __future__ import annotations

import time

# FreeCAD imports this file as ``document_lock`` while package callers use the
# qualified spelling.  Publish the first-loaded object under both names before
# importing its collaborators so the facade and every compatibility surface
# have one identity in either environment.
_MODULE_ALIASES = ("addon.FreeCADMCP.document_lock", "document_lock")

try:
    from addon.FreeCADMCP.document_lock_ops.module_aliases import (
        install_facade_aliases as _install_facade_aliases,
    )
    from addon.FreeCADMCP.document_lock_ops.module_aliases import (
        install_loaded_module_aliases as _install_loaded_module_aliases,
    )
except ImportError:  # pragma: no cover - flat FreeCAD addon layout
    from document_lock_ops.module_aliases import (
        install_facade_aliases as _install_facade_aliases,
    )
    from document_lock_ops.module_aliases import (
        install_loaded_module_aliases as _install_loaded_module_aliases,
    )

_install_facade_aliases(__name__, _MODULE_ALIASES)

try:
    from addon.FreeCADMCP.document_lock_ops.acquire_lease import acquire_lease
    from addon.FreeCADMCP.document_lock_ops.agent_mutation_ops import (
        begin_agent_mutation_scope,
        end_agent_mutation_scope,
        get_agent_mutation_context,
    )
    from addon.FreeCADMCP.document_lock_ops.constants import (
        LEASE_TTL_SECONDS,
        SIDECAR_SUFFIX,
    )
    from addon.FreeCADMCP.document_lock_ops.document_lock_observer import (
        DocumentLockObserver,
    )
    from addon.FreeCADMCP.document_lock_ops.eligibility import _is_eligible_target
    from addon.FreeCADMCP.document_lock_ops.facade_surfaces import (
        configure_facade_surfaces,
    )
    from addon.FreeCADMCP.document_lock_ops.file_baseline import (
        file_baseline,
        pid_alive,
        verify_saved_file,
    )
    from addon.FreeCADMCP.document_lock_ops.force_release_stale_lock import (
        force_release_stale_lock,
    )
    from addon.FreeCADMCP.document_lock_ops.gui_callback import set_gui_update_callback
    from addon.FreeCADMCP.document_lock_ops.heartbeat_lease import heartbeat_lease
    from addon.FreeCADMCP.document_lock_ops.internal_snapshot_save_ops import (
        begin_internal_snapshot_save_scope,
        end_internal_snapshot_save_scope,
        is_internal_snapshot_save,
    )
    from addon.FreeCADMCP.document_lock_ops.lease_record import LeaseRecord
    from addon.FreeCADMCP.document_lock_ops.lease_state import LeaseState
    from addon.FreeCADMCP.document_lock_ops.mark_save_verified import mark_save_verified
    from addon.FreeCADMCP.document_lock_ops.mark_user_intervened import (
        mark_user_intervened,
    )
    from addon.FreeCADMCP.document_lock_ops.migrate_lease_key import migrate_lease_key
    from addon.FreeCADMCP.document_lock_ops.mutation_check import (
        annotate_read_result,
        check_mutation_allowed,
        check_persisted_mutation_allowed,
    )
    from addon.FreeCADMCP.document_lock_ops.registration import (
        register_lock_feature,
        register_observer,
    )
    from addon.FreeCADMCP.document_lock_ops.registry_queries import (
        _is_stale,
        discover_sidecar_leases,
        ensure_session_id,
        get_lease,
        get_session_id_for_name,
        inspect_persisted_compatibility_lease,
        list_leases,
        reset_registry_for_tests,
        resolve_doc_key,
    )
    from addon.FreeCADMCP.document_lock_ops.release_lease import release_lease
    from addon.FreeCADMCP.document_lock_ops.request_identity import (
        begin_agent_mutation,
        clear_request_identity,
        end_agent_mutation,
        get_request_identity,
        is_agent_mutating,
        set_request_identity,
    )
    from addon.FreeCADMCP.document_lock_ops.settings import (
        _read_settings,
        _settings_path_impl,
        configure_runtime_lease_mode,
        get_runtime_lease_mode,
        is_enabled,
        is_enforcement_enabled,
    )
    from addon.FreeCADMCP.document_lock_ops.sidecar_io import (
        _public_sidecar_payload,
        sidecar_path_for,
    )
    from addon.FreeCADMCP.document_lock_ops.transition_lease import transition_lease
    from addon.FreeCADMCP.document_lock_ops.verb_classification import (
        VERB_CLASSIFICATION,
    )
    from addon.FreeCADMCP.document_lock_ops.verb_kind import VerbKind
    from addon.FreeCADMCP.document_lock_ops.verb_ops import (
        classify_verb,
        extract_referenced_documents_from_code,
        validate_unsafe_execute_scope,
    )
except ImportError:
    from document_lock_ops.acquire_lease import acquire_lease
    from document_lock_ops.agent_mutation_ops import (
        begin_agent_mutation_scope,
        end_agent_mutation_scope,
        get_agent_mutation_context,
    )
    from document_lock_ops.constants import LEASE_TTL_SECONDS, SIDECAR_SUFFIX
    from document_lock_ops.document_lock_observer import DocumentLockObserver
    from document_lock_ops.eligibility import _is_eligible_target
    from document_lock_ops.facade_surfaces import configure_facade_surfaces
    from document_lock_ops.file_baseline import (
        file_baseline,
        pid_alive,
        verify_saved_file,
    )
    from document_lock_ops.force_release_stale_lock import force_release_stale_lock
    from document_lock_ops.gui_callback import set_gui_update_callback
    from document_lock_ops.heartbeat_lease import heartbeat_lease
    from document_lock_ops.internal_snapshot_save_ops import (
        begin_internal_snapshot_save_scope,
        end_internal_snapshot_save_scope,
        is_internal_snapshot_save,
    )
    from document_lock_ops.lease_record import LeaseRecord
    from document_lock_ops.lease_state import LeaseState
    from document_lock_ops.mark_save_verified import mark_save_verified
    from document_lock_ops.mark_user_intervened import mark_user_intervened
    from document_lock_ops.migrate_lease_key import migrate_lease_key
    from document_lock_ops.mutation_check import (
        annotate_read_result,
        check_mutation_allowed,
        check_persisted_mutation_allowed,
    )
    from document_lock_ops.registration import register_lock_feature, register_observer
    from document_lock_ops.registry_queries import (
        _is_stale,
        discover_sidecar_leases,
        ensure_session_id,
        get_lease,
        get_session_id_for_name,
        inspect_persisted_compatibility_lease,
        list_leases,
        reset_registry_for_tests,
        resolve_doc_key,
    )
    from document_lock_ops.release_lease import release_lease
    from document_lock_ops.request_identity import (
        begin_agent_mutation,
        clear_request_identity,
        end_agent_mutation,
        get_request_identity,
        is_agent_mutating,
        set_request_identity,
    )
    from document_lock_ops.settings import (
        _read_settings,
        _settings_path_impl,
        configure_runtime_lease_mode,
        get_runtime_lease_mode,
        is_enabled,
        is_enforcement_enabled,
    )
    from document_lock_ops.sidecar_io import _public_sidecar_payload, sidecar_path_for
    from document_lock_ops.transition_lease import transition_lease
    from document_lock_ops.verb_classification import VERB_CLASSIFICATION
    from document_lock_ops.verb_kind import VerbKind
    from document_lock_ops.verb_ops import (
        classify_verb,
        extract_referenced_documents_from_code,
        validate_unsafe_execute_scope,
    )

_install_loaded_module_aliases()

# §3.3 compatibility shims — monkeypatch surfaces bind through the facade.
_settings_path = _settings_path_impl
configure_facade_surfaces(
    time_module_provider=lambda: time,
    settings_path_provider=lambda: _settings_path(),
    pid_alive_provider=lambda pid: pid_alive(pid),
    facade_namespace=globals(),
    default_settings_path=_settings_path,
    default_pid_alive=pid_alive,
)

__all__ = [
    "LEASE_TTL_SECONDS",
    "SIDECAR_SUFFIX",
    "VERB_CLASSIFICATION",
    "DocumentLockObserver",
    "LeaseRecord",
    "LeaseState",
    "VerbKind",
    "_is_eligible_target",
    "_is_stale",
    "_public_sidecar_payload",
    "_read_settings",
    "_settings_path",
    "acquire_lease",
    "annotate_read_result",
    "begin_agent_mutation",
    "begin_agent_mutation_scope",
    "begin_internal_snapshot_save_scope",
    "check_mutation_allowed",
    "check_persisted_mutation_allowed",
    "classify_verb",
    "clear_request_identity",
    "configure_runtime_lease_mode",
    "discover_sidecar_leases",
    "end_agent_mutation",
    "end_agent_mutation_scope",
    "end_internal_snapshot_save_scope",
    "ensure_session_id",
    "extract_referenced_documents_from_code",
    "file_baseline",
    "force_release_stale_lock",
    "get_agent_mutation_context",
    "get_lease",
    "get_request_identity",
    "get_runtime_lease_mode",
    "get_session_id_for_name",
    "heartbeat_lease",
    "inspect_persisted_compatibility_lease",
    "is_agent_mutating",
    "is_enabled",
    "is_enforcement_enabled",
    "is_internal_snapshot_save",
    "list_leases",
    "mark_save_verified",
    "mark_user_intervened",
    "migrate_lease_key",
    "pid_alive",
    "register_lock_feature",
    "register_observer",
    "release_lease",
    "reset_registry_for_tests",
    "resolve_doc_key",
    "set_gui_update_callback",
    "set_request_identity",
    "sidecar_path_for",
    "time",
    "transition_lease",
    "validate_unsafe_execute_scope",
    "verify_saved_file",
]
