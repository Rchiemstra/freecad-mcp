import logging
import threading  # noqa: F401 - §3.3 test monkeypatch surface
import time  # noqa: F401 - §3.3 test monkeypatch surface
import uuid  # noqa: F401 - §3.3 test monkeypatch surface
import xmlrpc.client  # noqa: F401 - §3.3 test monkeypatch surface

# §3.3 compatibility shims — keep old import paths working.
from .freecad_client_ops.constants import DIRECT_READ_METHODS as _DIRECT_READ_METHODS  # noqa: F401
from .freecad_client_ops.constants import (
    SCREENSHOT_SUPPORT_CHECK as _SCREENSHOT_SUPPORT_CHECK,  # noqa: F401
)
from .freecad_client_ops.facade_bindings import bind_freecad_connection
from .freecad_client_ops.freecad_connection import FreeCADConnection
from .freecad_client_ops.generated_execute import (  # noqa: F401
    _generated_execute_signature,
    _sign_generated_execute_params,
)
from .freecad_client_ops.instance_mismatch_error import InstanceMismatchError
from .freecad_client_ops.proxy_lane import ProxyLane as _ProxyLane  # noqa: F401
from .freecad_client_ops.proxy_method import ProxyMethod as _ProxyMethod  # noqa: F401
from .freecad_client_ops.rpc_invocation_error import RpcInvocationError
from .freecad_client_ops.timeout_transport import (
    TimeoutTransport as _TimeoutTransport,  # noqa: F401
)

logger = logging.getLogger("FreeCADMCPserver")

bind_freecad_connection(FreeCADConnection)

__all__ = [
    "FreeCADConnection",
    "InstanceMismatchError",
    "RpcInvocationError",
]
