import uuid
from dataclasses import dataclass, field
from typing import Any

from .freecad_client import FreeCADConnection
from .rpc_session import RpcAuthenticationSession


@dataclass
class ServerState:
    only_text_feedback: bool = False
    rpc_host: str = "127.0.0.1"
    rpc_port: int = 9875
    # When set, the client verifies the FreeCAD addon answering on rpc_port
    # reports this same instance id before trusting the connection. Guards
    # against dialing the wrong FreeCAD instance when running isolated instances
    # in parallel (ports are configurable but otherwise interchangeable).
    # Note: this is the expected FreeCAD add-on instance id, not the MCP
    # process's own authentication runtime identity (see mcp_instance_id).
    instance_id: str | None = None
    freecad_connection: FreeCADConnection | None = None
    # Stable MCP-process identity used by the authenticated transport handshake.
    mcp_instance_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    mcp_client_label: str = "freecad-mcp"
    mcp_pid: int = 0
    mcp_host: str = ""
    mcp_process_started_at: str = ""
    instance_manifest_path: str | None = None
    instance_manifest_path_identity: str | None = None
    auth_file: str | None = None
    instance_manifest: Any | None = field(default=None, repr=False)
    authenticated_manifest: Any | None = field(default=None, repr=False)
    rpc_session_id: str | None = None
    rpc_session_expires_at: str | None = None
    rpc_session: RpcAuthenticationSession = field(
        default_factory=RpcAuthenticationSession,
        repr=False,
    )
    compatibility_warnings: list[str] = field(default_factory=list)
    mcp_task_requests: dict[str, str] = field(default_factory=dict)
