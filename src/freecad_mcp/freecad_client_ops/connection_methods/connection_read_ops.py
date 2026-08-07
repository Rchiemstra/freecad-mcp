"""Declarative shim — generated connection method lives in generated/capabilities."""

from freecad_mcp.generated.capabilities.connection_methods import (
    connection_read_ops as _generated,
)

ping = _generated.ping
check_rpc_sync = _generated.check_rpc_sync
get_instance_info = _generated.get_instance_info
supports_rpc_parameter = _generated.supports_rpc_parameter
verify_instance = _generated.verify_instance
create_document = _generated.create_document
create_object = _generated.create_object
edit_object = _generated.edit_object
inspect_references = _generated.inspect_references
repair_references = _generated.repair_references
delete_object = _generated.delete_object
reload_document = _generated.reload_document
insert_part_from_library = _generated.insert_part_from_library
execute_code = _generated.execute_code
get_worker_status = _generated.get_worker_status
cancel_worker_job = _generated.cancel_worker_job
execute_code_async = _generated.execute_code_async

__all__ = [  # noqa: RUF022
    'ping',
    'check_rpc_sync',
    'get_instance_info',
    'supports_rpc_parameter',
    'verify_instance',
    'create_document',
    'create_object',
    'edit_object',
    'inspect_references',
    'repair_references',
    'delete_object',
    'reload_document',
    'insert_part_from_library',
    'execute_code',
    'get_worker_status',
    'cancel_worker_job',
    'execute_code_async',
]
