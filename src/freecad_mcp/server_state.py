from dataclasses import dataclass, field
from typing import Any
import uuid

from .freecad_client import FreeCADConnection
from .lease_manager import LeaseClientManager


@dataclass
class ServerState:
    only_text_feedback: bool = False
    rpc_host: str = "127.0.0.1"
    rpc_port: int = 9875
    # When set, the client verifies the FreeCAD addon answering on rpc_port
    # reports this same instance id before trusting the connection. Guards
    # against dialing the wrong FreeCAD instance when running isolated instances
    # in parallel (ports are configurable but otherwise interchangeable).
    # Note: this is the *expected FreeCAD addon* instance id, not the MCP
    # process's own lease identity (see mcp_instance_id).
    instance_id: str | None = None
    freecad_connection: FreeCADConnection | None = None
    # Stable MCP-process identity for document leases (created once in main()).
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
    # Live FreeCAD Document.Name -> addon-issued session UUID. Names are
    # diagnostic aliases only; credentials remain keyed by the UUID.
    document_sessions: dict[str, str] = field(default_factory=dict)
    # v2 credentials and authenticated-session state. Raw tokens are redacted
    # from repr/status and routed per request by this manager.
    lease_manager: LeaseClientManager = field(default_factory=LeaseClientManager)
    # Legacy v1 doc_key → token map retained until server.py is migrated to the
    # manager. New code must not use this shared dictionary for request routing.
    lease_tokens: dict[str, str] = field(default_factory=dict, repr=False)
