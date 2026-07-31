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

When FreeCAD core DocumentMutationAuthority is active (patched FreeCAD),
unscoped mutations are denied before execution.  This observer remains as an
audit/UI fallback and as the sole fence on stock FreeCAD builds.
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


def _is_internal_snapshot_save(document: Any, filename: Any) -> bool:
    """Recognize only the exact synchronous save callback of worker saveCopy."""

    module = sys.modules.get("document_lock") or sys.modules.get(
        "addon.FreeCADMCP.document_lock"
    )
    if module is None:
        return False
    checker = getattr(module, "is_internal_snapshot_save", None)
    if not callable(checker):
        return False
    try:
        return bool(checker(document, filename))
    except Exception:
        logger.debug("internal snapshot save attribution failed", exc_info=True)
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


def _has_accepted_baseline(record: Any) -> bool:
    if not isinstance(record, Mapping):
        return False
    document_state = record.get("document_state")
    if not isinstance(document_state, Mapping):
        return False
    baseline = document_state.get("baseline")
    return isinstance(baseline, Mapping) and bool(baseline.get("sha256"))


IDENTITY_REGISTRATION_BRANCH_REGISTRATION_FAILED = "registration_failed"
IDENTITY_REGISTRATION_BRANCH_POST_INSPECTION_FAILED = (
    "post_registration_inspection_failed"
)


@dataclass(frozen=True)
class IdentityRegistrationFailure:
    """Token-free diagnostics when live document registration returns None."""

    document_name: str
    failure_branch: str
    drifted_fields: tuple[str, ...] = ()
    identity_refresh_attempted: bool = False
    identity_refresh_refused_reason: str = ""

    def to_details(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "document_name": self.document_name,
            "failure_branch": self.failure_branch,
            "identity_refresh_attempted": self.identity_refresh_attempted,
        }
        if self.drifted_fields:
            payload["drifted_fields"] = list(self.drifted_fields)
        if (
            self.identity_refresh_attempted
            and self.identity_refresh_refused_reason
        ):
            payload["identity_refresh_refused_reason"] = (
                self.identity_refresh_refused_reason
            )
        return payload


def _document_display_name(document: Any) -> str:
    name = getattr(document, "Name", None) or getattr(document, "Label", None)
    return str(name or "<unknown>")


def _identity_refresh_refusal_code(exc: BaseException) -> str:
    message = str(exc).lower()
    if "content hash" in message:
        return "IDENTITY_REFRESH_CONTENT_HASH_CHANGED"
    if "name or canonical path" in message or "name or path" in message:
        return "IDENTITY_REFRESH_NAME_OR_PATH_CHANGED"
    if "baseline is missing" in message or (
        "baseline" in message and "missing" in message
    ):
        return "IDENTITY_REFRESH_BASELINE_MISSING"
    if (
        "not a registered live document proxy" in message
        or "replacement proxy" in message
    ):
        return "IDENTITY_REFRESH_REPLACEMENT_PROXY"
    if "lease state" in message or "current lease state" in message:
        return "IDENTITY_REFRESH_LEASE_STATE_FORBIDS"
    code = str(getattr(exc, "code", "") or "").strip()
    if code:
        return code
    return "IDENTITY_REFRESH_REFUSED"


def _collect_identity_drift_fields(identities: Any, document: Any) -> tuple[str, ...]:
    registered_session_uuid = getattr(identities, "registered_session_uuid", None)
    if not callable(registered_session_uuid):
        return ()
    try:
        session_uuid = registered_session_uuid(document)
    except Exception as exc:
        # Identity modules may be loaded under both `document_lease` and
        # `addon.FreeCADMCP.document_lease`, so catch by message/name instead of
        # a single UnknownDocumentError class object.
        if (
            type(exc).__name__ == "UnknownDocumentError"
            or "not a registered live document proxy" in str(exc).casefold()
        ):
            return ("unregistered_proxy",)
        raise
    try:
        observed = identities.inspect_registered_document(session_uuid, document)
    except Exception as exc:
        if "not the registered live document proxy" in str(exc):
            return ("replacement_proxy",)
        return ("live_proxy_inspection_failed",)
    try:
        expected = identities.resolve(session_uuid)
    except Exception:
        return ("registered_identity_unavailable",)
    drifted: list[str] = []
    if observed.name != expected.name:
        drifted.append("name")
    if observed.comparison_key != expected.comparison_key:
        drifted.append("comparison_key")
    if observed.file_identity != expected.file_identity:
        drifted.append("file_identity")
    return tuple(drifted)


def register_live_document_recovery(
    service: Any, document: Any
) -> tuple[Any, Mapping[str, Any] | None, IdentityRegistrationFailure | None]:
    """Register one live proxy, then conservatively import its v2 sidecar."""

    identities = getattr(service, "identity_service", None)
    if identities is None:
        raise RuntimeError("document identity service is unavailable")
    document_name = _document_display_name(document)
    drifted_fields = _collect_identity_drift_fields(identities, document)
    identity_refresh_attempted = False
    identity_refresh_refused_reason = ""
    registration_failed = False
    try:
        identity = identities.register_document(document)
    except Exception:
        registration_failed = True
        repairer = getattr(
            service,
            "repair_registered_document_identity",
            None,
        )
        if callable(repairer):
            identity_refresh_attempted = True
            try:
                identity = repairer(document=document)
                registration_failed = False
            except Exception as repair_exc:
                identity_refresh_refused_reason = _identity_refresh_refusal_code(
                    repair_exc
                )
                logger.debug(
                    "baseline-preserving identity repair was not applicable",
                    exc_info=True,
                )
        if registration_failed:
            # A locally observed close leaves its exact identity and sidecar
            # authoritative. Rebind only through the service's one-shot close
            # marker; never classify registration errors by import-sensitive
            # exception identity or resolve by name into an arbitrary proxy.
            rebinder = getattr(
                service,
                "rebind_closed_recovery_document",
                None,
            )
            if not callable(rebinder):
                logger.debug(
                    "live document registration failed; skip recovery import",
                    exc_info=True,
                )
            else:
                try:
                    identity = rebinder(document=document)
                    registration_failed = False
                except Exception:
                    logger.debug(
                        "closed live document rebind failed; try orphan repair",
                        exc_info=True,
                    )
    orphan_refresher = getattr(
        service,
        "refresh_orphaned_foreign_document_identity",
        None,
    )
    should_try_orphan_repair = registration_failed
    if not should_try_orphan_repair:
        raw_path = str(getattr(document, "FileName", "") or "").strip()
        get_foreign = getattr(service, "get_foreign_recovery", None)
        if raw_path and not os.path.lexists(f"{raw_path}.freecad-mcp.lock"):
            try:
                should_try_orphan_repair = bool(
                    callable(get_foreign)
                    and get_foreign(identity.session_uuid) is not None
                )
            except Exception:
                should_try_orphan_repair = False
    if should_try_orphan_repair and callable(orphan_refresher):
        try:
            identity = orphan_refresher(document=document)
            registration_failed = False
        except Exception:
            logger.debug(
                "orphaned foreign document identity repair was not applicable",
                exc_info=True,
            )
    if registration_failed:
        return (
            None,
            None,
            IdentityRegistrationFailure(
                document_name=document_name,
                failure_branch=IDENTITY_REGISTRATION_BRANCH_REGISTRATION_FAILED,
                drifted_fields=drifted_fields,
                identity_refresh_attempted=identity_refresh_attempted,
                identity_refresh_refused_reason=identity_refresh_refused_reason,
            ),
        )
    # This second, non-mutating inspection is the evidence passed to the
    # recovery service; a stale/replaced proxy or unexpected path fails here.
    try:
        live_identity = identities.inspect_registered_document(
            identity.session_uuid, document
        )
    except Exception:
        logger.debug(
            "registered live proxy mismatch; skip recovery import",
            exc_info=True,
        )
        return (
            None,
            None,
            IdentityRegistrationFailure(
                document_name=document_name,
                failure_branch=IDENTITY_REGISTRATION_BRANCH_POST_INSPECTION_FAILED,
                drifted_fields=_collect_identity_drift_fields(identities, document)
                or drifted_fields
                or ("live_proxy_inspection_failed",),
                identity_refresh_attempted=identity_refresh_attempted,
                identity_refresh_refused_reason=identity_refresh_refused_reason,
            ),
        )
    if not live_identity.canonical_path:
        return live_identity, None, None
    sidecar = Path(f"{live_identity.canonical_path}.freecad-mcp.lock")
    if not os.path.lexists(sidecar):
        return live_identity, None, None
    if service.get(live_identity.session_uuid) is not None:
        return live_identity, None, None
    get_foreign = getattr(service, "get_foreign_recovery", None)
    if callable(get_foreign):
        existing = get_foreign(live_identity.session_uuid)
        if existing is not None:
            return live_identity, None, None
    importer = getattr(service, "import_adjacent_foreign_recovery", None)
    if not callable(importer):
        return live_identity, None, None
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
        return live_identity, None, None
    return live_identity, imported, None


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
        self._pending_unscoped_gui_save: dict[str, int] = {}

    def _is_agent_attributed(self, document: Any, identity: Any | None = None) -> bool:
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
                identity = identity_service.resolve(selector)
            except Exception:
                continue
            # A queued observer callback may outlive the App::Document proxy
            # that produced it.  Name/path resolution alone would then find a
            # newly reopened replacement and let the stale callback update its
            # dirty state.  Production identity services can prove the exact
            # registered proxy; lightweight compatibility providers that do
            # not expose that check retain their previous behavior.
            inspector = getattr(
                identity_service,
                "inspect_registered_document",
                None,
            )
            if callable(inspector):
                try:
                    inspector(identity.session_uuid, document)
                except Exception:
                    continue
            return identity
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

    @staticmethod
    def _refresh_unleased_saved_identity(
        service: Any,
        identity: Any,
        document: Any,
    ) -> None:
        """Refresh an exact registered proxy after an unleased GUI save."""

        identities = getattr(service, "identity_service", None)
        refresher = getattr(identities, "refresh_saved_document", None)
        if not callable(refresher):
            return
        try:
            refreshed = refresher(document)
            if refreshed.session_uuid != identity.session_uuid:
                raise RuntimeError("saved document identity changed its live session")
        except Exception:
            logger.warning(
                "unable to refresh unleased GUI-saved document identity",
                exc_info=True,
            )

    def _takeover_unscoped_change(
        self,
        service: Any,
        identity: Any,
        document: Any,
        *,
        kind: str,
        detail: str,
        dirty: bool | None,
    ) -> Any:
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
        try:
            from document_lease import core_authority

            core_authority.bump_takeover(document)
        except Exception:
            logger.debug("core mutation takeover sync failed", exc_info=True)
        self._notify(
            kind=kind,
            identity=identity,
            reason=reason,
            dirty=dirty,
            record=record,
        )
        return record

    def _preserve_or_fence_after_gui_save(
        self,
        service: Any,
        identity: Any,
        document: Any,
        *,
        kind: str,
        detail: str,
        dirty: bool | None,
        trigger: str,
    ) -> Any:
        inplace_refresher = getattr(
            service,
            "try_baseline_preserving_document_identity_refresh",
            None,
        )
        refreshed = None
        if callable(inplace_refresher):
            try:
                refreshed = inplace_refresher(
                    identity.session_uuid,
                    document=document,
                    trigger=trigger,
                )
            except Exception:
                logger.debug(
                    "baseline-preserving save refresh failed",
                    exc_info=True,
                )
        if refreshed is not None:
            return refreshed
        return self._takeover_unscoped_change(
            service,
            identity,
            document,
            kind=kind,
            detail=detail,
            dirty=dirty,
        )

    def _handle(
        self,
        document: Any,
        kind: str,
        *,
        detail: str = "",
        force: bool = False,
        refresh_saved_identity: bool = False,
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
                try:
                    current = service.get(identity.session_uuid)
                except Exception:
                    logger.debug(
                        "unable to inspect selected document lease", exc_info=True
                    )
                    return None
                if current is None:
                    if refresh_saved_identity:
                        # A completed GUI save is authoritative evidence for
                        # refresh_saved_document's narrow exact-proxy,
                        # same-name, same-path file-identity update. Without a
                        # lease record there is no recovery document to update.
                        self._refresh_unleased_saved_identity(
                            service,
                            identity,
                            document,
                        )
                    return None
                # Attribution is accepted only on the executing GUI thread
                # when this exact live-document identity intersects the
                # active request's declared scope.  A mismatched nested
                # request poisons the context, causing this check to fail and
                # the owner to be fenced below.
                if not force and self._is_agent_attributed(document, identity):
                    return None
                dirty = _document_dirty(document)
                if dirty is None:
                    # Observer callbacks arrive during/after a change.  An
                    # unreadable GUI dirty flag can never be persisted as
                    # clean evidence after an unscoped mutation.
                    dirty = True
                recovery_state = _record_state(current)
                is_recovery_state = recovery_state in {
                    "USER_INTERVENED",
                    "UNLOCKED_DIRTY",
                }
                is_save_start = kind == "save" and not refresh_saved_identity
                is_save_finish = kind == "save" and refresh_saved_identity
                pending_close_save = (
                    kind == "document close"
                    and refresh_saved_identity
                    and identity.session_uuid in self._pending_unscoped_gui_save
                )
                record = current
                if is_recovery_state:
                    updater = getattr(service, "update_local_dirty", None)
                    if callable(updater):
                        try:
                            record = updater(identity.session_uuid, dirty=dirty)
                        except Exception:
                            logger.debug(
                                "unable to refresh local recovery dirty state",
                                exc_info=True,
                            )
                elif is_save_start:
                    # Fence immediately when finish-save cannot yet prove a
                    # baseline-preserving rewrite: no accepted baseline, or the
                    # live document is still dirty and content may change.
                    if _has_accepted_baseline(current) and dirty is False:
                        self._pending_unscoped_gui_save[identity.session_uuid] = (
                            id(document)
                        )
                    else:
                        self._pending_unscoped_gui_save.pop(
                            identity.session_uuid, None
                        )
                        record = self._takeover_unscoped_change(
                            service,
                            identity,
                            document,
                            kind=kind,
                            detail=detail,
                            dirty=dirty,
                        )
                elif is_save_finish or pending_close_save:
                    self._pending_unscoped_gui_save.pop(
                        identity.session_uuid, None
                    )
                    trigger = (
                        "gui_save_finish"
                        if is_save_finish
                        else "gui_save_close_without_finish"
                    )
                    record = self._preserve_or_fence_after_gui_save(
                        service,
                        identity,
                        document,
                        kind=kind,
                        detail=detail,
                        dirty=dirty,
                        trigger=trigger,
                    )
                else:
                    record = self._takeover_unscoped_change(
                        service,
                        identity,
                        document,
                        kind=kind,
                        detail=detail,
                        dirty=dirty,
                    )
                if refresh_saved_identity:
                    recovery_state = _record_state(record)
                    if recovery_state in {
                        "USER_INTERVENED",
                        "UNLOCKED_DIRTY",
                    }:
                        refresher = getattr(
                            service,
                            "refresh_local_recovery_document_identity",
                            None,
                        )
                        if callable(refresher):
                            try:
                                record = refresher(
                                    identity.session_uuid,
                                    document=document,
                                )
                            except Exception:
                                # Keep the takeover fence authoritative. A later
                                # RPC or restart must still fail closed rather than
                                # treating an unverified replacement as the same
                                # file.
                                logger.warning(
                                    "unable to refresh GUI-saved document identity",
                                    exc_info=True,
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

    def _refresh_finished_save(self, document: Any) -> Any | None:
        """Refresh recovery state after FreeCAD finishes clearing ``Modified``.

        Some supported FreeCAD builds emit ``slotFinishSaveDocument`` before
        the document's dirty flag is cleared.  This queued second pass may
        update only an already-fenced local recovery record; it must never turn
        a normally attributed owner save into a delayed takeover.
        """

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
                current = service.get(identity.session_uuid)
                if current is None:
                    self._refresh_unleased_saved_identity(
                        service,
                        identity,
                        document,
                    )
                    return None
                recovery_state = _record_state(current)
                is_recovery_state = recovery_state in {
                    "USER_INTERVENED",
                    "UNLOCKED_DIRTY",
                }
                dirty = _document_dirty(document)
                record = current
                if dirty is not None:
                    if is_recovery_state:
                        updater = getattr(service, "update_local_dirty", None)
                        if callable(updater):
                            record = updater(identity.session_uuid, dirty=dirty)
                    elif recovery_state in {
                        "LOCKED_IDLE",
                        "LOCKED_EDITING",
                        "LOCKED_RECOMPUTING",
                        "LOCKED_SAVING",
                        "LOCKED_ERROR",
                        "ACQUIRING",
                        "STALE",
                    }:
                        inplace_refresher = getattr(
                            service,
                            "try_baseline_preserving_document_identity_refresh",
                            None,
                        )
                        if callable(inplace_refresher):
                            try:
                                refreshed = inplace_refresher(
                                    identity.session_uuid,
                                    document=document,
                                    trigger="gui_save_finish_deferred",
                                )
                                if refreshed is not None:
                                    record = refreshed
                            except Exception:
                                logger.debug(
                                    "deferred baseline-preserving refresh failed",
                                    exc_info=True,
                                )
                if is_recovery_state:
                    refresher = getattr(
                        service,
                        "refresh_local_recovery_document_identity",
                        None,
                    )
                    if callable(refresher):
                        record = refresher(
                            identity.session_uuid,
                            document=document,
                        )
                return record
        except Exception:
            logger.warning(
                "unable to refresh completed FreeCAD save",
                exc_info=True,
            )
            return None

    # App::DocumentObserverPython callbacks.  The before/after pairs are
    # intentionally both present: availability and ordering vary across
    # supported FreeCAD builds, while takeover itself is idempotent.

    def slotCreatedDocument(self, document):  # noqa: N802
        service = get_runtime_service(self._service_provider)
        if service is None:
            return None
        # FreeCAD can emit this callback for a file being opened before its
        # final FileName has been attached to the live proxy. Registering that
        # provisional "unsaved" identity poisons the later path assertion.
        # Saved documents are registered once their path is observable by the
        # normal lazy status/acquire path; genuinely unsaved documents need no
        # adjacent-sidecar recovery at creation time.
        if not str(getattr(document, "FileName", "") or "").strip():
            return None
        try:
            identity, imported, _failure = register_live_document_recovery(
                service, document
            )
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
        if _is_internal_snapshot_save(document, filename):
            return None
        return self._handle(document, "save", detail=str(filename or ""))

    def slotFinishSaveDocument(self, document, filename):  # noqa: N802
        if _is_internal_snapshot_save(document, filename):
            return None
        record = self._handle(
            document,
            "save",
            detail=str(filename or ""),
            refresh_saved_identity=True,
        )
        # FreeCAD 1.2/26.3 on Windows clears ``Document.Modified`` only after
        # this callback returns. Queue a bounded second pass only when the
        # synchronous pass still observes dirty/unknown state.
        if _document_dirty(_document_from_subject(document)) is not False:
            try:
                self._notification_queue(lambda: self._refresh_finished_save(document))
            except Exception:
                logger.warning(
                    "completed-save refresh queue failed",
                    exc_info=True,
                )
        return record

    def slotDeletedDocument(self, document):  # noqa: N802
        # A leased document retains one-shot reopen authority; an unlocked
        # document is unregistered so opening it again gets a fresh identity.
        document = _document_from_subject(document)
        # Some supported builds do not emit the finish-save callback in every
        # close/application-shutdown sequence. Refresh the exact proxy's
        # same-path identity here as a final bounded opportunity before
        # retaining the one-shot reopen marker.
        record = self._handle(
            document,
            "document close",
            refresh_saved_identity=True,
        )
        if document is None:
            return record
        try:
            service = get_runtime_service(self._service_provider)
            if service is None:
                return record
            identity = self._identity_for_document(service, document)
            closer = getattr(service, "handle_document_closed", None)
            if identity is None or not callable(closer):
                return record
            closed = closer(identity.session_uuid, document=document)
            return record if record is not None else closed
        except Exception:
            logger.warning(
                "unable to retain or unregister closed document identity",
                exc_info=True,
            )
            return record

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
