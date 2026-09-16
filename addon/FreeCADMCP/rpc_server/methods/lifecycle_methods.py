"""Lifecycle / control-plane RPC methods bound on ``FreeCADRPC``."""

from .lifecycle_methods_ops.control_cancel import cancel_request
from .lifecycle_methods_ops.control_status import (
    check_rpc_sync,
    get_instance_info,
    get_request_status,
    ping,
)
from .cad_methods_ops.close_document import rpc_close_document as close_document
from .cad_methods_ops.create_document import rpc_create_document as create_document
from .lifecycle_methods_ops.document_gui import (
    close_document_gui,
    create_document_gui,
    reload_document_gui,
)
from .lifecycle_methods_ops.screenshot import save_active_screenshot
from .lifecycle_methods_ops.worker_ops import (
    cancel_worker_job,
    get_parts_list,
    get_worker_status,
    shutdown_rpc_server,
)

__all__ = [
    "cancel_request",
    "cancel_worker_job",
    "check_rpc_sync",
    "close_document",
    "close_document_gui",
    "create_document",
    "create_document_gui",
    "get_instance_info",
    "get_parts_list",
    "get_request_status",
    "get_worker_status",
    "ping",
    "reload_document_gui",
    "save_active_screenshot",
    "shutdown_rpc_server",
]
