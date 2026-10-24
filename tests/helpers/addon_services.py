"""Document-owner and RPC doubles for the shared add-on bridge tests."""
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock
import threading

from freecad_mcp.addon_services import Registry
from addon.FreeCADMCP.collaboration_api import CollaborationAPI
from addon.FreeCADMCP.rpc_server.methods import addon_services as rpc
from addon.FreeCADMCP.rpc_server.methods.dispatch_helpers_ops.dispatch_core import dispatch

class NativeDocument:
    """Model native admission, owner dispatch and document rollback, not CAD geometry."""
    def __init__(self, name="Target", *, allowed=True, status=None):
        self.Name = name
        self.allowed = allowed
        self.status = status
        self.value = 0
        self.rolled_back = False
        self.owner = None

    def commitCompatibilityMutation(self, callback, *, structural, recompute, postcondition):
        assert structural is True and recompute is True
        def commit():
            self.owner = threading.get_ident()
            # Native lease/CAS refusal occurs before apply, including query services.
            if not self.allowed:
                return {"status": "Conflict", "committed": False}
            before = self.value
            try:
                callback()
                assert postcondition() is True
            except Exception:
                self.value = before
                self.rolled_back = True
                raise  # CollaborationAPI recognizes this exact exception as rollback proof.
            return self.status if self.status is not None else {"status": "Committed", "committed": True}
        with ThreadPoolExecutor(max_workers=1) as owner:
            return owner.submit(commit).result()


def registry_with(callback, *, access="mutation"):
    registry = Registry()
    registry.register("Example", "1", [{"name": "run", "access": access,
                      "input_schema": {"type": "object", "properties": {
                          "value": {"type": "integer", "minimum": 0, "maximum": 9}},
                          "required": ["value"]}}], {"run": callback})
    return registry


def host(document, registry):
    lookup = Mock(side_effect=lambda name: document if name == document.Name else None)
    validate = Mock()
    collaborators = SimpleNamespace(freecad=SimpleNamespace(AddonServices=registry),
                                    compatibility_api=CollaborationAPI(document_lookup=lookup),
                                    validate_document_invariants=validate)
    class Host:
        list_addons = rpc.list_addons
        describe_addon = rpc.describe_addon
        invoke_addon_operation = rpc.invoke_addon_operation
        _dispatch = dispatch
        _cad_collaborators = collaborators
        def _dispatch_gui(self, callback):
            value = callback()
            return value.await_result() if hasattr(value, "await_result") else value
    return Host(), lookup, validate
