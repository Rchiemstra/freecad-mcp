from dataclasses import dataclass

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
    instance_id: str | None = None
    freecad_connection: FreeCADConnection | None = None
