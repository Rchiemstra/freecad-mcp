from dataclasses import dataclass, field
import uuid

from .freecad_client import FreeCADConnection


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
    # doc_key → lease token held by this MCP process
    lease_tokens: dict[str, str] = field(default_factory=dict)
