"""Per-document renewable write lease for MCP agents.

Pure/unit-testable core: lease registry, atomic sidecar lock files, staleness
checks, and Save As / first-save key migration. FreeCAD and Qt are imported
lazily so the module loads under the stubbed unit harness.

When ``enable_document_lock`` is false (default), nothing is registered, no
sidecars are written, and callers should treat this module as inert.
"""

from __future__ import annotations

import sys
import time

# FreeCAD adds this addon directory directly to ``sys.path`` and imports this
# file as ``document_lock``.  Package-aware callers (including the test suite)
# import the same file as ``addon.FreeCADMCP.document_lock``.  Without an early
# alias Python executes the file twice, producing two lease registries, two
# settings functions, and two request-identity thread locals.  Whichever name
# loads first owns the single module object; publishing both names here makes
# every later import resolve to that same object in either environment.
_CANONICAL_MODULE_NAME = "addon.FreeCADMCP.document_lock"
_FREECAD_MODULE_NAME = "document_lock"
_MODULE_ALIASES = (_CANONICAL_MODULE_NAME, _FREECAD_MODULE_NAME)


def _install_module_aliases() -> None:
    current = sys.modules.get(__name__)
    if current is None:  # pragma: no cover - import machinery always sets it
        return

    owner = next(
        (
            module
            for alias in _MODULE_ALIASES
            if (module := sys.modules.get(alias)) is not None
            and module is not current
        ),
        current,
    )
    for alias in _MODULE_ALIASES:
        sys.modules[alias] = owner


_install_module_aliases()

try:
    from .document_lock_ops.module_aliases import install_module_aliases, install_package_aliases
except ImportError:
    from document_lock_ops.module_aliases import install_module_aliases, install_package_aliases

try:
    from .document_lock_ops.acquire_lease import acquire_lease
    from .document_lock_ops.agent_mutation_ops import (
        begin_agent_mutation_scope,
        end_agent_mutation_scope,
        get_agent_mutation_context,
    )
    from .document_lock_ops.constants import LEASE_TTL_SECONDS, SIDECAR_SUFFIX
    from .document_lock_ops.document_lock_observer import DocumentLockObserver
    from .document_lock_ops.eligibility import _is_eligible_target
    from .document_lock_ops.file_baseline import (
        file_baseline,
        pid_alive,
        verify_saved_file,
    )
    from .document_lock_ops.force_release_stale_lock import force_release_stale_lock
    from .document_lock_ops.gui_callback import set_gui_update_callback
    from .document_lock_ops.heartbeat_lease import heartbeat_lease
    from .document_lock_ops.internal_snapshot_save_ops import (
        begin_internal_snapshot_save_scope,
        end_internal_snapshot_save_scope,
        is_internal_snapshot_save,
    )
    from .document_lock_ops.lease_record import LeaseRecord
    from .document_lock_ops.lease_state import LeaseState
    from .document_lock_ops.mark_save_verified import mark_save_verified
    from .document_lock_ops.mark_user_intervened import mark_user_intervened
    from .document_lock_ops.migrate_lease_key import migrate_lease_key
    from .document_lock_ops.mutation_check import (
        annotate_read_result,
        check_mutation_allowed,
        check_persisted_mutation_allowed,
    )
    from .document_lock_ops.registration import register_lock_feature, register_observer
    from .document_lock_ops.registry_queries import (
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
    from .document_lock_ops.release_lease import release_lease
    from .document_lock_ops.request_identity import (
        begin_agent_mutation,
        clear_request_identity,
        end_agent_mutation,
        get_request_identity,
        is_agent_mutating,
        set_request_identity,
    )
    from .document_lock_ops.settings import (
        _read_settings,
        _settings_path_impl,
        configure_runtime_lease_mode,
        get_runtime_lease_mode,
        is_enabled,
        is_enforcement_enabled,
    )
    from .document_lock_ops.sidecar_io import _public_sidecar_payload, sidecar_path_for
    from .document_lock_ops.transition_lease import transition_lease
    from .document_lock_ops.verb_classification import VERB_CLASSIFICATION
    from .document_lock_ops.verb_kind import VerbKind
    from .document_lock_ops.verb_ops import (
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

install_package_aliases()

for _mod_name in list(sys.modules):
    if _mod_name.startswith("document_lock_ops.") or _mod_name.startswith(
        "addon.FreeCADMCP.document_lock_ops."
    ):
        install_module_aliases(_mod_name)

# §3.3 compatibility shims — monkeypatch surfaces bind through the facade.
_settings_path = _settings_path_impl

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
