"""FreeCAD observers that fence a lease after an unscoped GUI mutation.

The observer deliberately has no import-time dependency on FreeCAD, Qt, the
RPC server, or the legacy lock module.  A running RPC server is discovered at
event time through a provider, so installing the observer before auto-start is
safe.  Likewise, GUI refreshes are emitted through a queued callback only;
observer callbacks never manipulate widgets themselves.

FreeCAD's Python observers report changes after (or while) they happen and do
not provide a universal mutation veto.  Consequently this module's job is to
fence the previous owner immediately: ``DocumentLeaseService.takeover`` bumps
the generation, rotates away from the old token digest, persists
``USER_INTERVENED``, and intentionally leaves the sidecar in place.
"""

from __future__ import annotations

import importlib
import logging
import os
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

try:
    from document_state import document_modified_state
except ImportError:
    from addon.FreeCADMCP.document_state import document_modified_state


logger = logging.getLogger("FreeCADMCP.document_lease.observer")

ServiceProvider = Callable[[], Any | None]
AgentMutationChecker = Callable[[str], bool]
DocumentProvider = Callable[[], Any | None]
NotificationCallback = Callable[["LeaseObserverEvent"], None]
NotificationQueue = Callable[[Callable[[], None]], None]


@dataclass(frozen=True)
class LeaseObserverEvent:
    """Token-free notification emitted after an owner has been fenced."""

    kind: str
    document_name: str
    document_session_uuid: str
    canonical_path: str | None
    reason: str
    dirty: bool | None
    state: str
    generation: int | None


def _default_service_provider() -> Any | None:
    """Find the already-loaded RPC module without importing it eagerly."""

    candidates = (
        "rpc_server.rpc_server",
        "addon.FreeCADMCP.rpc_server.rpc_server",
    )
    for module_name in candidates:
        module = sys.modules.get(module_name)
        if module is not None:
            service = getattr(module, "document_lease_service", None)
            if service is not None:
                return service

    # FreeCAD's addon loader can expose the child module as an attribute of
    # the short package name without retaining its fully-qualified alias.
    package = sys.modules.get("rpc_server")
    module = getattr(package, "rpc_server", None) if package is not None else None
    return getattr(module, "document_lease_service", None) if module else None


def get_runtime_service(provider: ServiceProvider | None = None) -> Any | None:
    """Return the current lease service, or ``None`` when RPC is not running."""

    try:
        return (provider or _default_service_provider)()
    except Exception:
        logger.debug("lease service provider failed", exc_info=True)
        return None


def _default_agent_mutation_checker(key: str) -> bool:
    """Delegate attribution to the legacy request-scoped mutation context."""

    module = sys.modules.get("document_lock") or sys.modules.get(
        "addon.FreeCADMCP.document_lock"
    )
    if module is None:
        try:
            module = importlib.import_module("document_lock")
        except Exception:
            try:
                module = importlib.import_module("addon.FreeCADMCP.document_lock")
            except Exception:
                return False
    checker = getattr(module, "is_agent_mutating", None)
    if not callable(checker):
        return False
    try:
        return bool(checker(key))
    except Exception:
        logger.debug("agent mutation attribution failed for %r", key, exc_info=True)
        return False


def _default_selected_document_provider() -> Any | None:
    module = sys.modules.get("FreeCAD")
    if module is None:
        try:
            module = importlib.import_module("FreeCAD")
        except Exception:
            return None
    return getattr(module, "ActiveDocument", None)


def _qt_or_direct_queue(callback: Callable[[], None]) -> None:
    """Queue through Qt when available, with a headless-safe fallback."""

    qt_core = None
    for package_name in ("PySide", "PySide2", "PySide6"):
        try:
            package = importlib.import_module(package_name)
            qt_core = getattr(package, "QtCore", None)
            if qt_core is None:
                qt_core = importlib.import_module(f"{package_name}.QtCore")
            break
        except Exception:
            continue
    timer = getattr(qt_core, "QTimer", None) if qt_core is not None else None
    single_shot = getattr(timer, "singleShot", None) if timer is not None else None
    if callable(single_shot):
        single_shot(0, callback)
    else:
        # Pure-Python and FreeCADCmd runs have no widgets to protect.  Keeping
        # this fallback makes notification behavior testable without Qt.
        callback()


def _document_from_subject(subject: Any) -> Any | None:
    """Resolve App::Document from an App object, GUI view provider, or doc."""

    if subject is None:
        return None
    if getattr(subject, "Name", None) and hasattr(subject, "FileName"):
        return subject
    document = getattr(subject, "Document", None)
    if document is not None:
        return document
    app_object = getattr(subject, "Object", None)
    document = getattr(app_object, "Document", None)
    if document is not None:
        return document
    get_document = getattr(subject, "getDocument", None)
    if callable(get_document):
        try:
            document = get_document()
        except Exception:
            document = None
        if document is not None:
            # Gui::Document.getDocument() may return either the App document or
            # a name depending on the FreeCAD build.  A name alone cannot be
            # resolved here without importing FreeCAD, so leave that case to
            # the active-document fallback.
            if not isinstance(document, str):
                return document
    return None


def _document_keys(document: Any, identity: Any | None = None) -> tuple[str, ...]:
    """Return exact aliases against which GUI request scope is checked."""

    values: list[str] = []
    if identity is not None:
        for attribute in (
            "session_uuid",
            "name",
            "canonical_path",
            "comparison_key",
        ):
            value = str(getattr(identity, attribute, "") or "").strip()
            if value and value not in values:
                values.append(value)
    name = str(getattr(document, "Name", "") or "").strip()
    if name:
        if name not in values:
            values.append(name)
    filename = str(getattr(document, "FileName", "") or "").strip()
    if filename:
        values.append(filename)
        try:
            resolved = str(Path(filename).resolve())
            if resolved not in values:
                values.append(resolved)
            normalized = os.path.normcase(resolved)
            if normalized not in values:
                values.append(normalized)
        except (OSError, RuntimeError, ValueError):
            pass
    return tuple(values)


def _document_dirty(document: Any) -> bool | None:
    return document_modified_state(document)


def _record_state(record: Any) -> str:
    if isinstance(record, Mapping):
        lease = record.get("lease")
        value = (
            lease.get("state", "")
            if isinstance(lease, Mapping)
            else record.get("state", "")
        )
    else:
        value = getattr(record, "state", "")
    return str(getattr(value, "value", value) or "")


def _record_generation(record: Any) -> int | None:
    if isinstance(record, Mapping):
        value = record.get("generation")
    else:
        value = getattr(record, "generation", None)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def register_live_document_recovery(
    service: Any, document: Any
) -> tuple[Any, Mapping[str, Any] | None]:
    """Register one live proxy, then conservatively import its v2 sidecar."""

    identities = getattr(service, "identity_service", None)
    if identities is None:
        raise RuntimeError("document identity service is unavailable")
    try:
        identity = identities.register_document(document)
    except Exception:
        identity = identities.resolve(
            {"document_name": str(getattr(document, "Name", "") or "")}
        )
    # This second, non-mutating inspection is the evidence passed to the
    # recovery service; a stale/replaced proxy or unexpected path fails here.
    live_identity = identities.inspect_registered_document(
        identity.session_uuid, document
    )
    if not live_identity.canonical_path:
        return live_identity, None
    sidecar = Path(f"{live_identity.canonical_path}.freecad-mcp.lock")
    if not os.path.lexists(sidecar):
        return live_identity, None
    if service.get(live_identity.session_uuid) is not None:
        return live_identity, None
    get_foreign = getattr(service, "get_foreign_recovery", None)
    if callable(get_foreign):
        existing = get_foreign(live_identity.session_uuid)
        if existing is not None:
            return live_identity, None
    importer = getattr(service, "import_adjacent_foreign_recovery", None)
    if not callable(importer):
        return live_identity, None
    try:
        imported = importer(
            live_identity.session_uuid,
            live_document=live_identity,
        )
    except Exception:
        # Import is optional discovery, never recovery. Preserve every byte of
        # malformed/unknown/mismatched authority and keep the document usable
        # only through the existing fail-closed sidecar/status paths.
        logger.warning(
            "unable to import adjacent document recovery sidecar",
            exc_info=True,
        )
        return live_identity, None
    return live_identity, imported


class LeaseObserver:
    """Application document observer for unscoped modelling changes."""

    def __init__(
        self,
        *,
        service_provider: ServiceProvider | None = None,
        agent_mutation_checker: AgentMutationChecker | None = None,
        selected_document_provider: DocumentProvider | None = None,
        notification_callback: NotificationCallback | None = None,
        notification_queue: NotificationQueue | None = None,
    ) -> None:
        self._service_provider = service_provider or _default_service_provider
        self._agent_mutation_checker = (
            agent_mutation_checker or _default_agent_mutation_checker
        )
        self._selected_document_provider = (
            selected_document_provider or _default_selected_document_provider
        )
        self._notification_callback = notification_callback
        self._notification_queue = notification_queue or _qt_or_direct_queue
        self._event_lock = threading.RLock()

    def _is_agent_attributed(
        self, document: Any, identity: Any | None = None
    ) -> bool:
        for key in _document_keys(document, identity):
            try:
                if self._agent_mutation_checker(key):
                    return True
            except Exception:
                logger.debug("mutation checker failed", exc_info=True)
        return False

    @staticmethod
    def _identity_for_document(service: Any, document: Any) -> Any | None:
        identity_service = getattr(service, "identity_service", None)
        if identity_service is None:
            return None
        name = str(getattr(document, "Name", "") or "").strip()
        filename = str(getattr(document, "FileName", "") or "").strip()
        selectors: list[dict[str, str]] = []
        if name:
            selectors.append({"document_name": name})
        if filename:
            selectors.append({"canonical_path": filename})
        for selector in selectors:
            try:
                return identity_service.resolve(selector)
            except Exception:
                continue
        return None

    def _notify(
        self,
        *,
        kind: str,
        identity: Any,
        reason: str,
        dirty: bool | None,
        record: Any,
    ) -> None:
        callback = self._notification_callback
        if callback is None:
            return
        event = LeaseObserverEvent(
            kind=kind,
            document_name=str(getattr(identity, "name", "") or ""),
            document_session_uuid=str(getattr(identity, "session_uuid", "") or ""),
            canonical_path=getattr(identity, "canonical_path", None),
            reason=reason,
            dirty=dirty,
            state=_record_state(record),
            generation=_record_generation(record),
        )

        def deliver() -> None:
            try:
                callback(event)
            except Exception:
                logger.warning("lease observer notification failed", exc_info=True)

        try:
            self._notification_queue(deliver)
        except Exception:
            # A GUI queue failure must never escape into FreeCAD's observer
            # bridge.  Do not fall back to touching the GUI synchronously.
            logger.warning("lease observer notification queue failed", exc_info=True)

    def _handle(
        self,
        document: Any,
        kind: str,
        *,
        detail: str = "",
        force: bool = False,
    ) -> Any | None:
        document = _document_from_subject(document)
        if document is None:
            return None
        try:
            service = get_runtime_service(self._service_provider)
            if service is None:
                return None
            with self._event_lock:
                identity = self._identity_for_document(service, document)
                if identity is None:
                    return None
                # Attribution is accepted only on the executing GUI thread
                # when this exact live-document identity intersects the
                # active request's declared scope.  A mismatched nested
                # request poisons the context, causing this check to fail and
                # the owner to be fenced below.
                if not force and self._is_agent_attributed(document, identity):
                    return None
                try:
                    current = service.get(identity.session_uuid)
                except Exception:
                    logger.debug(
                        "unable to inspect selected document lease", exc_info=True
                    )
                    return None
                if current is None:
                    return None
                dirty = _document_dirty(document)
                if dirty is None:
                    # Observer callbacks arrive during/after a change.  An
                    # unreadable GUI dirty flag can never be persisted as
                    # clean evidence after an unscoped mutation.
                    dirty = True
                if _record_state(current) in {
                    "USER_INTERVENED",
                    "UNLOCKED_DIRTY",
                }:
                    updater = getattr(service, "update_local_dirty", None)
                    if callable(updater):
                        try:
                            return updater(identity.session_uuid, dirty=dirty)
                        except Exception:
                            logger.debug(
                                "unable to refresh local recovery dirty state",
                                exc_info=True,
                            )
                    return current
                reason = f"Unscoped FreeCAD {kind} detected"
                if detail:
                    clean_detail = " ".join(str(detail).split())[:512]
                    if clean_detail:
                        reason += f": {clean_detail}"
                reason = reason[:2048]
                record = service.takeover(
                    identity.session_uuid,
                    dirty=dirty,
                    reason=reason,
                )
                self._notify(
                    kind=kind,
                    identity=identity,
                    reason=reason,
                    dirty=dirty,
                    record=record,
                )
                return record
        except Exception:
            # FreeCAD catches observer exceptions, but logging and containing
            # them here avoids noisy Report View tracebacks and preserves the
            # original modelling action's control flow.
            logger.warning("unable to fence unscoped FreeCAD change", exc_info=True)
            return None

    def _handle_selected(self, kind: str, *, detail: str = "") -> Any | None:
        try:
            document = self._selected_document_provider()
        except Exception:
            logger.debug("selected document provider failed", exc_info=True)
            return None
        return self._handle(document, kind, detail=detail)

    # App::DocumentObserverPython callbacks.  The before/after pairs are
    # intentionally both present: availability and ordering vary across
    # supported FreeCAD builds, while takeover itself is idempotent.

    def slotCreatedDocument(self, document):  # noqa: N802
        service = get_runtime_service(self._service_provider)
        if service is None:
            return None
        try:
            identity, imported = register_live_document_recovery(service, document)
            if imported is not None:
                self._notify(
                    kind="foreign recovery import",
                    identity=identity,
                    reason="Imported adjacent v2 recovery authority",
                    dirty=_document_dirty(document),
                    record=imported,
                )
            return imported
        except Exception:
            # Malformed, unknown, mismatched, or inaccessible records remain
            # untouched and continue to block via the adjacent sidecar.
            logger.warning(
                "unable to import adjacent document recovery sidecar",
                exc_info=True,
            )
            return None

    def slotBeforeChangeObject(self, obj, prop):  # noqa: N802
        return self._handle(obj, "object property change", detail=str(prop))

    def slotChangedObject(self, obj, prop):  # noqa: N802
        return self._handle(obj, "object property change", detail=str(prop))

    def slotCreatedObject(self, obj):  # noqa: N802
        return self._handle(obj, "object creation")

    def slotDeletedObject(self, obj):  # noqa: N802
        return self._handle(obj, "object deletion")

    def slotAppendDynamicProperty(self, container, prop):  # noqa: N802
        # DocumentObserverPython supplies the owning PropertyContainer and
        # property name, not the App::Property instance itself.
        return self._handle(
            container,
            "dynamic property addition",
            detail=str(prop),
        )

    def slotRemoveDynamicProperty(self, container, prop):  # noqa: N802
        return self._handle(
            container,
            "dynamic property removal",
            detail=str(prop),
        )

    def slotChangePropertyEditor(self, container, prop):  # noqa: N802
        return self._handle(
            container,
            "property editor change",
            detail=str(prop),
        )

    def slotBeforeAddingDynamicExtension(  # noqa: N802
        self, container, extension
    ):
        return self._handle(
            container,
            "dynamic extension addition",
            detail=str(extension),
        )

    def slotAddedDynamicExtension(self, container, extension):  # noqa: N802
        return self._handle(
            container,
            "dynamic extension addition",
            detail=str(extension),
        )

    def slotBeforeChangeDocument(self, document, prop):  # noqa: N802
        return self._handle(document, "document property change", detail=str(prop))

    def slotChangedDocument(self, document, prop):  # noqa: N802
        return self._handle(document, "document property change", detail=str(prop))

    def slotRelabelDocument(self, document):  # noqa: N802
        return self._handle(document, "document relabel")

    def slotUndoDocument(self, document):  # noqa: N802
        return self._handle(document, "undo")

    def slotRedoDocument(self, document):  # noqa: N802
        return self._handle(document, "redo")

    def slotUndo(self):  # noqa: N802
        return self._handle_selected("undo")

    def slotRedo(self):  # noqa: N802
        return self._handle_selected("redo")

    def slotBeforeRecomputeDocument(self, document):  # noqa: N802
        return self._handle(document, "recompute")

    def slotRecomputedDocument(self, document):  # noqa: N802
        return self._handle(document, "recompute")

    def slotRecomputedObject(self, obj):  # noqa: N802
        return self._handle(obj, "object recompute")

    def slotOpenTransaction(self, document, name):  # noqa: N802
        return self._handle(document, "transaction open", detail=str(name))

    def slotCommitTransaction(self, document):  # noqa: N802
        return self._handle(document, "transaction commit")

    def slotAbortTransaction(self, document):  # noqa: N802
        return self._handle(document, "transaction abort")

    def slotBeforeCloseTransaction(self, abort):  # noqa: N802
        action = "transaction abort" if abort else "transaction commit"
        return self._handle_selected(action)

    def slotCloseTransaction(self, abort):  # noqa: N802
        action = "transaction abort" if abort else "transaction commit"
        return self._handle_selected(action)

    def slotStartSaveDocument(self, document, filename):  # noqa: N802
        return self._handle(document, "save", detail=str(filename or ""))

    def slotFinishSaveDocument(self, document, filename):  # noqa: N802
        return self._handle(document, "save", detail=str(filename or ""))

    def slotDeletedDocument(self, document):  # noqa: N802
        # Do not unregister identity or remove any sidecar here.  The retained
        # USER_INTERVENED record is the recovery authority after a user close.
        return self._handle(document, "document close")

    def take_over_selected_document(
        self, *, reason: str = "Local user selected Take Over"
    ) -> Any | None:
        try:
            document = self._selected_document_provider()
        except Exception:
            logger.debug("selected document provider failed", exc_info=True)
            return None
        return self._handle(document, "manual takeover", detail=reason, force=True)


class LeaseGuiObserver:
    """Narrow GUI observer: edit-mode entry/exit, not camera or selection."""

    def __init__(self, app_observer: LeaseObserver) -> None:
        self._app_observer = app_observer

    def slotInEdit(self, view_provider):  # noqa: N802
        return self._app_observer._handle(view_provider, "GUI edit-mode entry")

    def slotResetEdit(self, view_provider):  # noqa: N802
        return self._app_observer._handle(view_provider, "GUI edit-mode exit")


_registration_lock = threading.RLock()
_app_observer: LeaseObserver | None = None
_gui_observer: LeaseGuiObserver | None = None
_registered_freecad: Any | None = None
_registered_freecad_gui: Any | None = None


def register_observer(
    *,
    freecad_module: Any | None = None,
    freecad_gui_module: Any | None = None,
    service_provider: ServiceProvider | None = None,
    agent_mutation_checker: AgentMutationChecker | None = None,
    selected_document_provider: DocumentProvider | None = None,
    notification_callback: NotificationCallback | None = None,
    notification_queue: NotificationQueue | None = None,
) -> LeaseObserver | None:
    """Register the App and optional GUI observers idempotently.

    Registration does not require a running RPC server.  The supplied service
    provider is evaluated only when a document event occurs.
    """

    global _app_observer, _gui_observer
    global _registered_freecad, _registered_freecad_gui
    with _registration_lock:
        if _app_observer is not None:
            return _app_observer
        if freecad_module is None:
            try:
                freecad_module = importlib.import_module("FreeCAD")
            except Exception:
                return None
        add_observer = getattr(freecad_module, "addDocumentObserver", None)
        if not callable(add_observer):
            return None
        observer = LeaseObserver(
            service_provider=service_provider,
            agent_mutation_checker=agent_mutation_checker,
            selected_document_provider=selected_document_provider,
            notification_callback=notification_callback,
            notification_queue=notification_queue,
        )
        add_observer(observer)
        _app_observer = observer
        _registered_freecad = freecad_module
        try:
            setattr(freecad_module, "_mcp_document_lease_observer", observer)
        except Exception:
            pass

        if freecad_gui_module is None:
            try:
                freecad_gui_module = importlib.import_module("FreeCADGui")
            except Exception:
                freecad_gui_module = None
        add_gui_observer = (
            getattr(freecad_gui_module, "addDocumentObserver", None)
            if freecad_gui_module is not None
            else None
        )
        if callable(add_gui_observer):
            gui_observer = LeaseGuiObserver(observer)
            try:
                add_gui_observer(gui_observer)
                _gui_observer = gui_observer
                _registered_freecad_gui = freecad_gui_module
                try:
                    setattr(
                        freecad_gui_module,
                        "_mcp_document_lease_gui_observer",
                        gui_observer,
                    )
                except Exception:
                    pass
            except Exception:
                logger.warning("unable to register GUI lease observer", exc_info=True)
        return observer


def unregister_observer() -> None:
    """Unregister both observers without changing any lease or sidecar."""

    global _app_observer, _gui_observer
    global _registered_freecad, _registered_freecad_gui
    with _registration_lock:
        app_observer = _app_observer
        gui_observer = _gui_observer
        freecad_module = _registered_freecad
        freecad_gui_module = _registered_freecad_gui
        _app_observer = None
        _gui_observer = None
        _registered_freecad = None
        _registered_freecad_gui = None

        remove_gui = (
            getattr(freecad_gui_module, "removeDocumentObserver", None)
            if freecad_gui_module is not None
            else None
        )
        if gui_observer is not None and callable(remove_gui):
            try:
                remove_gui(gui_observer)
            except Exception:
                logger.debug("unable to unregister GUI lease observer", exc_info=True)
        remove_app = (
            getattr(freecad_module, "removeDocumentObserver", None)
            if freecad_module is not None
            else None
        )
        if app_observer is not None and callable(remove_app):
            try:
                remove_app(app_observer)
            except Exception:
                logger.debug("unable to unregister App lease observer", exc_info=True)

        for module, attr, expected in (
            (freecad_module, "_mcp_document_lease_observer", app_observer),
            (
                freecad_gui_module,
                "_mcp_document_lease_gui_observer",
                gui_observer,
            ),
        ):
            try:
                if module is not None and getattr(module, attr, None) is expected:
                    delattr(module, attr)
            except Exception:
                pass


def take_over_selected_document(
    *,
    service_provider: ServiceProvider | None = None,
    selected_document_provider: DocumentProvider | None = None,
    notification_callback: NotificationCallback | None = None,
    notification_queue: NotificationQueue | None = None,
    reason: str = "Local user selected Take Over",
) -> Any | None:
    """Fence the active document for a confirmed local GUI takeover action."""

    observer = LeaseObserver(
        service_provider=service_provider,
        selected_document_provider=selected_document_provider,
        notification_callback=notification_callback,
        notification_queue=notification_queue,
    )
    return observer.take_over_selected_document(reason=reason)


__all__ = [
    "LeaseGuiObserver",
    "LeaseObserver",
    "LeaseObserverEvent",
    "get_runtime_service",
    "register_live_document_recovery",
    "register_observer",
    "take_over_selected_document",
    "unregister_observer",
]
