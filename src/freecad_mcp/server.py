"""FreeCAD MCP server façade (Phase 7 / 7D)."""

from __future__ import annotations

import logging
import threading
import uuid  # noqa: F401 - §3.3 test shims
import warnings
from types import MappingProxyType

from typing_extensions import TypedDict

from ._shared.protocol.constants import (  # noqa: F401 - §3.3 test shims
    REQUIRED_PROTOCOL_FEATURES,
)
from ._shared.protocol.handshake_request import (  # noqa: F401 - §3.3 test shims
    build_handshake_request_from_manifest,
)
from ._shared.protocol.handshake_response import (  # noqa: F401 - §3.3 test shims
    verify_handshake_response_from_manifest,
)
from ._shared.protocol.manifest import (  # noqa: F401 - §3.3 test shims
    load_instance_manifest,
    make_mcp_runtime_identity,
)
from ._shared.protocol.profile_secret import (  # noqa: F401 - §3.3 test shims
    load_profile_secret,
)
from .build_info import (  # noqa: F401 - §3.3 test / runtime shims
    build_id,
    event_schema_version,
    git_commit,
    git_dirty,
    package_version,
    protocol_version,
)
from .freecad_client import FreeCADConnection  # noqa: F401 - §3.3 test shims
from .instrumented_server import InstrumentedFastMCP
from .lease_manager import (  # noqa: F401 - §3.3 test shims
    STALE_RECOVERY_TRIGGER_HEARTBEAT,
    STALE_RECOVERY_TRIGGER_POST_TOOL,
    StaleLeaseRecoveryOrchestrator,
)
from .prompt_text import ASSET_CREATION_STRATEGY
from .server_ops.connection import get_freecad_connection
from .server_ops.heartbeat import lease_heartbeat_once as _lease_heartbeat_once  # noqa: F401
from .server_ops.lifespan import server_lifespan
from .server_ops.main_cli import main as _main_impl
from .server_ops.manifest_auth import (
    authenticate_connection as _authenticate_connection,  # noqa: F401
)
from .server_ops.manifest_auth import (
    refresh_authenticated_connection as _refresh_authenticated_connection,  # noqa: F401
)
from .server_ops.paths import path_identity as _path_identity
from .server_ops.session import session_needs_refresh as _session_needs_refresh  # noqa: F401
from .server_ops.stale_recovery_hooks import post_tool_stale_recovery
from .server_ops.stale_recovery_hooks import (
    post_tool_stale_recovery as _post_tool_stale_recovery,  # noqa: F401 - §3.3 test shims
)
from .server_ops.surfaces import (
    LEASE_HEARTBEAT_INTERVAL_S as _LEASE_HEARTBEAT_INTERVAL_S,  # noqa: F401
)
from .server_ops.tool_exports import __all__ as __all__
from .server_ops.tool_exports import bind_tool_exports
from .server_ops.tool_registration import register_tool_modules
from .server_state import ServerState
from .telemetry import emit_event  # noqa: F401 - §3.3 test shims
from .tools_register_order import REGISTER_TOOL_MODULES

logging.basicConfig(
    level=logging.WARNING, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("FreeCADMCPserver")
logger.setLevel(logging.INFO)

state = ServerState()
_connection_lock = threading.RLock()
stale_recovery = StaleLeaseRecoveryOrchestrator()


class DocumentSelectorInput(TypedDict, total=False):
    """Exact public fields accepted by document lifecycle selectors."""

    __pydantic_config__ = MappingProxyType({"extra": "forbid"})

    document_name: str
    document_session_uuid: str
    canonical_path: str


mcp = InstrumentedFastMCP(
    "FreeCADMCP",
    instructions="FreeCAD integration through the Model Context Protocol",
    lifespan=server_lifespan,
)
mcp.post_tool_completed_hook = post_tool_stale_recovery

try:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        mcp._mcp_server.experimental.enable_tasks()
except (AttributeError, ImportError):
    logger.info("MCP Tasks extension unavailable; synchronous fallback active")

mcp.task_request_canceller = (
    lambda request_id: get_freecad_connection()._notify_cancel_request(request_id)
)

_TOOL_EXPORTS = register_tool_modules(
    mcp,
    module_names=REGISTER_TOOL_MODULES,
    state=state,
    get_freecad_connection=get_freecad_connection,
    stale_recovery=stale_recovery,
    document_selector_input=DocumentSelectorInput,
)
bind_tool_exports(_TOOL_EXPORTS)
from .server_ops.tool_exports import *  # noqa: E402, F403


@mcp.prompt()
def asset_creation_strategy() -> str:
    return ASSET_CREATION_STRATEGY


def main() -> None:
    _main_impl(state=state, mcp=mcp, path_identity=_path_identity)


if __name__ == "__main__":
    main()
