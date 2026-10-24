"""Generic installed add-on services through the existing native commit boundary."""

from __future__ import annotations

from freecad_mcp.addon_services import ServiceContext, ServiceError

from .cad_methods_ops.native_commit_wait import defer_native_result

_REJECTED = {"StaleDocument", "InvalidPreparedEdit", "Conflict", "Cancelled",
             "Unsupported", "Busy", "ApplyFailed", "RecomputeFailed",
             "PostconditionFailed", "PublicationFailed"}
_ROLLED_BACK = {"ApplyFailed", "RecomputeFailed", "PostconditionFailed", "PublicationFailed"}


def _failure(code, message, *, committed=False, outcome="rejected", **details):
    return {"success": False, "error_code": str(code)[:96], "error": str(message)[:4096],
            "committed": committed, "outcome": outcome,
            "retry_safe": outcome == "rejected", **details}


def _registry(self):
    # Discovery belongs to trusted local startup, never a remote metadata read.
    registry = getattr(self._cad_collaborators.freecad, "AddonServices", None)
    if registry is None or getattr(registry, "protocol_version", None) != 1:
        raise ServiceError("ADDON_SERVICES_UNAVAILABLE", "The host service registry is not loaded.")
    return registry


def list_addons(self):
    """Read cached registration metadata without GUI or document access."""
    try:
        return {"success": True, "addons": _registry(self).list()}
    except ServiceError as exc:
        return _failure(exc.code, str(exc))


def describe_addon(self, addon_id):
    """Read one cached descriptor without running provider code."""
    try:
        if not isinstance(addon_id, str) or not addon_id:
            raise ServiceError("INVALID_ARGUMENT", "addon_id must be a nonempty string.")
        return {"success": True, "addon": _registry(self).describe(addon_id)}
    except ServiceError as exc:
        return _failure(exc.code, str(exc))


def run_addon_operation(bridge, registry, validate_document, doc_name, addon_id, operation, arguments):
    """Only native apply may call a provider; its return is provisional until commit."""
    if any(not isinstance(value, str) or not value.strip()
           for value in (doc_name, addon_id, operation)) or not isinstance(arguments, dict):
        return _failure("INVALID_ARGUMENT", "Supply doc_name, addon_id, operation and object arguments.")
    state = {"document": None, "applied": False, "validated": False, "result": None, "failure": None}
    cleanups = []

    def cleanup():
        while cleanups:
            callback = cleanups.pop()
            try:
                callback()
            except Exception:
                # Cleanup cannot turn a rejected/uncertain commit into success.
                pass

    def apply(document):
        state["document"] = document
        try:
            if getattr(document, "Name", None) != doc_name:
                raise ServiceError("DOCUMENT_IDENTITY_MISMATCH", "Native apply received a different document.")
            state["result"] = registry.invoke(
                addon_id, operation, arguments,
                context=ServiceContext(document=document, access="mutation", actor_id="mcp", on_rejected=cleanups.append),
            )
            state["applied"] = True
        except Exception as exc:
            state["failure"] = (exc if isinstance(exc, ServiceError) else
                                ServiceError("ADDON_OPERATION_FAILED", str(exc) or type(exc).__name__))
            # Native owns transaction rollback, including result validation errors.
            raise

    def postcondition(document):
        try:
            if document is not state["document"] or not state["applied"]:
                raise ServiceError("DOCUMENT_IDENTITY_MISMATCH", "Native callbacks must use one admitted document.")
            validate_document(document)
            state["validated"] = True
            return True
        except Exception as exc:
            state["failure"] = (exc if isinstance(exc, ServiceError) else
                                ServiceError("DOCUMENT_HEALTH_DEGRADED", str(exc) or type(exc).__name__))
            raise

    def interpret(terminal):
        native = terminal if isinstance(terminal, dict) else {}
        status = native.get("status")
        committed = native.get("committed")
        rollback_invalid = any(key in native and not isinstance(native[key], bool)
                               for key in ("rollback_failed", "rollback_succeeded"))
        rollback_failed = (status == "RollbackFailed" or native.get("rollback_failed") is True
                           or native.get("rollback_succeeded") is False)
        if not rollback_invalid and not rollback_failed:
            if (status == "Committed" and committed is True and "rollback_succeeded" not in native
                    and state["validated"] and state["failure"] is None):
                return {"success": True, "committed": True, "outcome": "committed", "retry_safe": False,
                        "document_name": doc_name, "addon_id": addon_id,
                        "operation": operation, "result": state["result"]}
            if committed is False and isinstance(status, str) and status in _REJECTED:
                cleanup()
                error = state["failure"] if status in {"ApplyFailed", "PostconditionFailed"} else None
                details = {"native_status": status}
                if status in _ROLLED_BACK:
                    details["rollback_succeeded"] = True
                    # Native rollback covers the document, not opaque external effects.
                    details["retry_safe"] = False
                return _failure(error.code if error else "NATIVE_COMPATIBILITY_MUTATION_REJECTED",
                                str(error) if error else str(native.get("message") or "Native commit rejected the operation."),
                                **details)
        cleanup()
        return _failure("ADDON_COMMIT_UNCERTAIN", "Native terminal status did not prove a successful add-on commit.",
                        committed=True if committed is True else None, outcome="uncertain",
                        native_status=status[:128] if isinstance(status, str) else None,
                        **({"rollback_failed": True, "rollback_succeeded": False} if rollback_failed else {}))

    try:
        native = bridge.commit_native_mutation(doc_name, apply, postcondition, structural=True)
    except LookupError as exc:
        cleanup()
        if state["document"] is None:
            return _failure("DOCUMENT_NOT_FOUND", str(exc))
        return _failure("ADDON_COMMIT_UNCERTAIN", str(exc), committed=None, outcome="uncertain")
    except Exception as exc:
        cleanup()
        return _failure("ADDON_COMMIT_UNCERTAIN", str(exc), committed=None, outcome="uncertain")

    pending = defer_native_result(native, interpret)
    if isinstance(pending, dict):
        return pending

    class PendingAddonCommit:
        def await_result(self, timeout=60.0):
            try:
                return pending.await_result(timeout)
            except Exception as exc:
                cleanup()
                return _failure("ADDON_COMMIT_UNCERTAIN", str(exc), committed=None, outcome="uncertain")

    return PendingAddonCommit()


def invoke_addon_operation(self, doc_name, addon_id, operation, arguments):
    """Invoke using native document authority and owner dispatch, even for queries."""
    try:
        registry = _registry(self)
    except ServiceError as exc:
        return _failure(exc.code, str(exc))
    collaborators = self._cad_collaborators
    # Require the native API itself; never fall back to executing plugin code.
    return self._dispatch_gui(lambda: run_addon_operation(
        collaborators.compatibility_api, registry, collaborators.validate_document_invariants,
        doc_name, addon_id, operation, arguments,
    ))
