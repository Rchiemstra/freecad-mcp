"""FreeCAD observers that fence a lease after an unscoped GUI mutation.

The observer deliberately has no import-time dependency on FreeCAD, Qt, the
RPC server, or the legacy lock module.  A running RPC server is discovered at
event time through a provider, so installing the observer before auto-start is
safe.  Likewise, GUI refreshes are emitted through a queued callback only;
observer callbacks never manipulate widgets themselves.

FreeCAD's Python observers report changes after (or while) they happen and do
not provide a universal mutation veto.  Consequently this module's job is to
fence the previous owner immediately: ``DocumentLeaseService.takeover`` bumps
the generation, rotates away from the old token digest, persists
``USER_INTERVENED``, and intentionally leaves the sidecar in place.

When FreeCAD core DocumentMutationAuthority is active (patched FreeCAD),
unscoped mutations are denied before execution.  This observer remains as an
audit/UI fallback and as the sole fence on stock FreeCAD builds.
"""

from __future__ import annotations

import threading
from typing import Any

# §3.3 compatibility shims — moved symbols keep their legacy import path.
from .observer_ops._log import logger
from .observer_ops.app_observer import LeaseObserver
from .observer_ops.document_helpers import document_dirty as _document_dirty  # noqa: F401
from .observer_ops.document_helpers import (
    document_display_name as _document_display_name,  # noqa: F401
)
from .observer_ops.document_helpers import (
    document_from_subject as _document_from_subject,  # noqa: F401
)
from .observer_ops.document_helpers import document_keys as _document_keys  # noqa: F401
from .observer_ops.events import (
    AgentMutationChecker,
    DocumentProvider,
    LeaseObserverEvent,
    NotificationCallback,
    NotificationQueue,
    ServiceProvider,
)
from .observer_ops.gui_observer import LeaseGuiObserver
from .observer_ops.identity_drift import (
    collect_identity_drift_fields as _collect_identity_drift_fields,  # noqa: F401
)
from .observer_ops.identity_drift import (
    identity_refresh_refusal_code as _identity_refresh_refusal_code,  # noqa: F401
)
from .observer_ops.identity_registration_failure import (
    IDENTITY_REGISTRATION_BRANCH_POST_INSPECTION_FAILED,
    IDENTITY_REGISTRATION_BRANCH_REGISTRATION_FAILED,
    IdentityRegistrationFailure,
)
from .observer_ops.live_document_recovery import register_live_document_recovery
from .observer_ops.record_helpers import (
    has_accepted_baseline as _has_accepted_baseline,  # noqa: F401
)
from .observer_ops.record_helpers import record_generation as _record_generation  # noqa: F401
from .observer_ops.record_helpers import record_state as _record_state  # noqa: F401
from .observer_ops.runtime_providers import (
    default_agent_mutation_checker as _default_agent_mutation_checker,  # noqa: F401
)
from .observer_ops.runtime_providers import (
    default_selected_document_provider as _default_selected_document_provider,  # noqa: F401
)
from .observer_ops.runtime_providers import (
    default_service_provider as _default_service_provider,
)
from .observer_ops.runtime_providers import (
    is_internal_snapshot_save as _is_internal_snapshot_save,  # noqa: F401
)
from .observer_ops.runtime_providers import qt_or_direct_queue as _qt_or_direct_queue  # noqa: F401

_registration_lock = threading.RLock()
_app_observer: LeaseObserver | None = None
_gui_observer: LeaseGuiObserver | None = None
_registered_freecad: Any | None = None
_registered_freecad_gui: Any | None = None

from .observer_ops.registration import (  # noqa: E402
    register_observer,
    take_over_selected_document,
    unregister_observer,
)


def get_runtime_service(provider: ServiceProvider | None = None) -> Any | None:
    """Return the current lease service, or ``None`` when RPC is not running."""

    try:
        return (provider or _default_service_provider)()
    except Exception:
        logger.debug("lease service provider failed", exc_info=True)
        return None


__all__ = [
    "IDENTITY_REGISTRATION_BRANCH_POST_INSPECTION_FAILED",
    "IDENTITY_REGISTRATION_BRANCH_REGISTRATION_FAILED",
    "AgentMutationChecker",
    "DocumentProvider",
    "IdentityRegistrationFailure",
    "LeaseGuiObserver",
    "LeaseObserver",
    "LeaseObserverEvent",
    "NotificationCallback",
    "NotificationQueue",
    "ServiceProvider",
    "get_runtime_service",
    "logger",
    "register_live_document_recovery",
    "register_observer",
    "take_over_selected_document",
    "unregister_observer",
]
