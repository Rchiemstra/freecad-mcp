"""Bridge FreeCAD core DocumentMutationAuthority with document leases.

Capabilities are short-lived and in-process only. Out-of-process MCP clients
continue to present lease credentials; after lease authorization the addon opens
a core capability for the duration of the GUI-thread mutation.

On FreeCAD builds without the mutation-authority API this module is a no-op so
cooperative observer fencing remains the fallback.
"""

from __future__ import annotations

# §3.3 compatibility shims — keep old import paths working.
from .core_authority_ops.capability import (
    capability_context_or_null,
    open_documents_mutation_capability,
    open_mutation_capability,
)
from .core_authority_ops.document import (
    core_authority_available,
    core_owner_api_available,
    resolve_document,
)
from .core_authority_ops.kinds import (
    CLOSE_MUTATION_KINDS,
    LIVE_MUTATION_KINDS,
    SAVE_MUTATION_KINDS,
    kinds_for_rpc_method,
)
from .core_authority_ops.lease_sync import (
    restore_authority_status,
    sync_clear_from_release,
    sync_gui_lease_takeover,
    sync_mcp_owner_verified,
    sync_owner_from_lease_record,
)
from .core_authority_ops.owner import (
    authority_status,
    bump_takeover,
    clear_owner,
    is_core_enforced,
    logger,
    set_mcp_owner,
)

__all__ = [
    "CLOSE_MUTATION_KINDS",
    "LIVE_MUTATION_KINDS",
    "SAVE_MUTATION_KINDS",
    "authority_status",
    "bump_takeover",
    "capability_context_or_null",
    "clear_owner",
    "core_authority_available",
    "core_owner_api_available",
    "is_core_enforced",
    "kinds_for_rpc_method",
    "logger",
    "open_documents_mutation_capability",
    "open_mutation_capability",
    "resolve_document",
    "restore_authority_status",
    "set_mcp_owner",
    "sync_clear_from_release",
    "sync_gui_lease_takeover",
    "sync_mcp_owner_verified",
    "sync_owner_from_lease_record",
]
