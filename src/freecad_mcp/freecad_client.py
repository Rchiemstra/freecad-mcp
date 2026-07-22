import contextvars
import hashlib
import hmac
import json
import logging
import threading
import xmlrpc.client
import uuid
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from .execute_options import ExecuteOptions
from .lease_manager import (
    LeaseClientManager,
    LeaseNotFoundError,
    RpcRequestContext,
)
from .template_resources import read_template_text


logger = logging.getLogger("FreeCADMCPserver")

_SCREENSHOT_SUPPORT_CHECK = read_template_text(
    "freecad_client/screenshot_support_check.py.txt"
)

_DIRECT_READ_METHODS = frozenset(
    {
        "ping",
        "check_rpc_sync",
        "get_instance_info",
        "get_worker_status",
        "cancel_worker_job",
        "get_document_lock",
        "list_document_locks",
        "inspect_references",
        "get_active_screenshot",
        "capture_view_sequence",
        "capture_view_sequence_to_disk",
        "refresh_view",
        "get_objects",
        "get_object",
        "get_parts_list",
        "list_documents",
        "open_document",
        "activate_document",
        "set_tree_expanded",
        "select_subshapes",
        "get_selection",
        "get_gui_state",
        "set_section_view",
        "spreadsheet_get_cells",
        "spreadsheet_list_aliases",
        "list_expressions",
        "diagnose_parametric",
    }
)


def _generated_execute_signature(
    *,
    session_token: str,
    request_id: str,
    code: str,
    options: Mapping[str, Any],
) -> str:
    """Authenticate the internal generated-code capability marker.

    The public MCP ``execute_code`` signature cannot supply this value.  It is
    added at the transport boundary and is bound to the immutable v2 request,
    exact code, operation id, and declared document scope.
    """

    affected = options.get("affected_documents") or ()
    payload = {
        "request_id": request_id,
        "operation_id": str(options.get("operation_id") or ""),
        "code_sha256": hashlib.sha256(code.encode("utf-8")).hexdigest(),
        "document": str(options.get("document") or ""),
        "affected_documents": sorted({str(item) for item in affected}),
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hmac.new(session_token.encode("utf-8"), canonical, hashlib.sha256)
    return f"hmac-sha256:{digest.hexdigest()}"


def _sign_generated_execute_params(
    method: str,
    params: Mapping[str, Any] | None,
    context: RpcRequestContext,
) -> Mapping[str, Any] | None:
    if method != "execute_code" or not isinstance(params, Mapping):
        return params
    raw_options = params.get("options")
    code = params.get("code")
    if (
        not isinstance(raw_options, Mapping)
        or not raw_options.get("generated_operation")
        or not isinstance(code, str)
    ):
        return params
    options = dict(raw_options)
    options["operation_signature"] = _generated_execute_signature(
        session_token=context.session_token,
        request_id=context.request_id,
        code=code,
        options=options,
    )
    signed = dict(params)
    signed["options"] = options
    return signed


class _TimeoutTransport(xmlrpc.client.Transport):
    """XML-RPC transport with a configurable socket timeout and MCP headers.

    The default Transport has no timeout, so a frozen FreeCAD GUI thread
    causes the MCP client to hang indefinitely (observed: 4+ minute waits).

    ``extra_headers`` are installed only while a serialized proxy lane owns the
    transport. This keeps the underlying HTTP connection reusable without
    allowing concurrent requests to overwrite one another's authentication.
    """

    def __init__(self, timeout: float = 30, **kwargs):
        super().__init__(**kwargs)
        self._timeout = timeout
        # Access is serialized by _ProxyLane.
        self.extra_headers: list[tuple[str, str]] = []

    def make_connection(self, host):
        conn = super().make_connection(host)
        conn.timeout = self._timeout
        return conn

    def send_headers(self, connection, headers):
        if self.extra_headers:
            # Prefer our identity headers; append after the stock ones
            headers = list(headers) + list(self.extra_headers)
        return super().send_headers(connection, headers)


class _ProxyMethod:
    """Dotted XML-RPC method bound to one serialized transport lane."""

    def __init__(self, lane: "_ProxyLane", name: str):
        self._lane = lane
        self._name = name

    def __getattr__(self, name: str) -> "_ProxyMethod":
        return type(self)(self._lane, f"{self._name}.{name}")

    def __call__(self, *args: Any) -> Any:
        return self._lane.call(self._name, *args)


class _ProxyLane:
    """Thread-safe ServerProxy lane with independent connection state.

    General work and control/heartbeat work use different instances so a long
    modelling call cannot hold the transport lock needed by a lease renewal.
    """

    def __init__(
        self,
        uri: str,
        timeout: float,
        header_provider: Callable[[str, tuple[Any, ...]], tuple[tuple[str, str], ...]],
    ) -> None:
        self._header_provider = header_provider
        self._lock = threading.RLock()
        self.transport = _TimeoutTransport(timeout=timeout)
        self._proxy = xmlrpc.client.ServerProxy(
            uri,
            allow_none=True,
            transport=self.transport,
        )

    def __getattr__(self, name: str) -> _ProxyMethod:
        if name.startswith("_"):
            raise AttributeError(name)
        return _ProxyMethod(self, name)

    def call(
        self,
        method: str,
        *args: Any,
        extra_headers: tuple[tuple[str, str], ...] = (),
    ) -> Any:
        with self._lock:
            # Header values are snapshotted only after this lane is exclusively
            # owned. Clear them afterwards so lease/session secrets do not
            # remain reachable through a cached transport.
            self.transport.extra_headers = list(
                self._header_provider(method, tuple(args))
            ) + list(extra_headers)
            try:
                target: Any = self._proxy
                for segment in method.split("."):
                    target = getattr(target, segment)
                return target(*args)
            finally:
                self.transport.extra_headers = []

    def close(self) -> None:
        with self._lock:
            self.transport.extra_headers = []
            self.transport.close()


class InstanceMismatchError(RuntimeError):
    """Raised when the FreeCAD addon on a port is not the expected instance."""


class RpcInvocationError(RuntimeError):
    """Credential-safe transport failure for an authenticated invocation."""

    def __init__(self, method: str, cause: BaseException) -> None:
        self.code = type(cause).__name__.upper()
        super().__init__(
            f"Authenticated RPC {method!r} failed ({type(cause).__name__})"
        )


class FreeCADConnection:
    def __init__(
        self,
        host: str = "localhost",
        port: int = 9875,
        timeout: float = 150,
        expected_instance_id: str | None = None,
        mcp_instance_id: str | None = None,
        mcp_client: str | None = None,
        mcp_pid: int | None = None,
        mcp_host: str | None = None,
    ):
        self._uri = f"http://{host}:{port}"
        self._timeout = timeout
        self._expected_instance_id = expected_instance_id
        self._mcp_instance_id = mcp_instance_id
        self._mcp_client = mcp_client
        self._mcp_pid = mcp_pid
        self._mcp_host = mcp_host
        self._rpc_port = port
        self._identity_lock = threading.RLock()
        self._base_headers: tuple[tuple[str, str], ...] = ()
        self._lease_manager: LeaseClientManager | None = None
        self._document_session_resolver: Callable[[str], str | None] | None = None
        self._session_refresher: Callable[[], None] | None = None
        # ContextVar keeps the deprecated header token isolated across threads
        # and asyncio tasks. New code must use RpcRequestContext/invoke_v2.
        self._legacy_lease_token: contextvars.ContextVar[str | None] = (
            contextvars.ContextVar(
                f"freecad_mcp_legacy_lease_token_{id(self)}", default=None
            )
        )
        self._refresh_headers()
        self.server = _ProxyLane(self._uri, timeout, self._request_headers_snapshot)
        self.control_server = _ProxyLane(
            self._uri,
            min(timeout, 30),
            self._request_headers_snapshot,
        )
        # Kept as a compatibility inspection hook for code that previously
        # reached into the connection's default transport.
        self._transport = self.server.transport
        self._disconnected = False

    def _refresh_headers(self) -> None:
        with self._identity_lock:
            headers: list[tuple[str, str]] = []
            if self._mcp_instance_id:
                headers.append(("X-MCP-Instance-Id", str(self._mcp_instance_id)))
            if self._mcp_client:
                headers.append(("X-MCP-Client", str(self._mcp_client)))
            if self._mcp_pid:
                headers.append(("X-MCP-Pid", str(self._mcp_pid)))
            if self._mcp_host:
                headers.append(("X-MCP-Host", str(self._mcp_host)))
            headers.append(("X-MCP-Rpc-Port", str(self._rpc_port)))
            self._base_headers = tuple(headers)

    def _request_headers_snapshot(
        self, method: str = "", args: tuple[Any, ...] = ()
    ) -> tuple[tuple[str, str], ...]:
        with self._identity_lock:
            headers = self._base_headers
            manager = self._lease_manager
            resolver = self._document_session_resolver
        # v2 carries its complete immutable authentication context in the
        # envelope.  Do not add a second, independently generated request id
        # or any lease credential headers to that call.
        if method in {"invoke_v2", "invoke_v2_control", "handshake_v2"}:
            return headers
        direct_read = (
            manager is not None
            and manager.connected
            and (
                method in _DIRECT_READ_METHODS
                or (
                    method == "execute_code"
                    and len(args) > 1
                    and isinstance(args[1], Mapping)
                    and bool(args[1].get("read_only", False))
                )
            )
        )
        if direct_read:
            context = manager.build_request_context(operation_name=method or "RPC read")
            return headers + (
                ("X-MCP-Session-Token", context.session_token),
                ("X-MCP-Request-Id", context.request_id),
                ("X-MCP-Lease-Credentials", "[]"),
            )
        token_var = getattr(self, "_legacy_lease_token", None)
        token = token_var.get() if token_var is not None else None
        if token:
            return headers + (("X-MCP-Lease-Token", str(token)),)
        if manager is not None and manager.connected:
            document_names: list[str] = []
            if (
                method == "execute_code"
                and len(args) > 1
                and isinstance(args[1], Mapping)
            ):
                options = args[1]
                primary = options.get("document")
                if isinstance(primary, str) and primary:
                    document_names.append(primary)
                for name in options.get("affected_documents") or ():
                    if isinstance(name, str) and name and name not in document_names:
                        document_names.append(name)
            elif args and isinstance(args[0], str):
                document_names.append(args[0])
            session_ids = []
            selector_argument = None
            if (
                method == "release_document_lock"
                and len(args) > 2
                and isinstance(args[2], Mapping)
            ):
                selector_argument = args[2]
            if (
                args
                and isinstance(args[0], Mapping)
                and method
                in {
                    "update_document_lock",
                    "save_document",
                    "save_document_as",
                    "finalize_document_edit",
                }
            ) or selector_argument is not None:
                selector = selector_argument or args[0]
                selected_session = selector.get("document_session_uuid")
                if isinstance(selected_session, str) and selected_session:
                    session_ids.append(selected_session)
                selected_name = selector.get("document_name")
                if isinstance(selected_name, str) and selected_name:
                    document_names.append(selected_name)
                selected_path = selector.get("canonical_path")
                if isinstance(selected_path, str) and selected_path:
                    selected = manager.get(canonical_path=selected_path)
                    if (
                        selected is not None
                        and selected.document_session_uuid not in session_ids
                    ):
                        session_ids.append(selected.document_session_uuid)
            if resolver is not None:
                for name in document_names:
                    session_uuid = resolver(name)
                    if session_uuid and session_uuid not in session_ids:
                        session_ids.append(session_uuid)
            try:
                context = manager.build_request_context(
                    document_session_uuids=session_ids,
                    operation_name=method or "RPC request",
                )
            except Exception:
                context = manager.build_request_context(
                    operation_name=method or "RPC request"
                )
            credential_payload = [item.to_wire() for item in context.lease_credentials]
            routed = headers + (
                ("X-MCP-Session-Token", context.session_token),
                ("X-MCP-Request-Id", context.request_id),
                (
                    "X-MCP-Lease-Credentials",
                    json.dumps(
                        credential_payload,
                        ensure_ascii=True,
                        separators=(",", ":"),
                    ),
                ),
            )
            if len(credential_payload) == 1:
                credential = credential_payload[0]
                routed += (
                    ("X-MCP-Lease-Id", credential["lease_id"]),
                    (
                        "X-MCP-Lease-Generation",
                        str(credential["generation"]),
                    ),
                    (
                        "X-MCP-Document-Session-Id",
                        credential["document_session_uuid"],
                    ),
                    ("X-MCP-Lease-Token", credential["token"]),
                )
            return routed
        return headers

    def configure_lease_routing(
        self,
        manager: LeaseClientManager,
        document_session_resolver: Callable[[str], str | None],
    ) -> None:
        """Install request-scoped session/credential routing for typed v1 calls."""

        with self._identity_lock:
            self._lease_manager = manager
            self._document_session_resolver = document_session_resolver

    def configure_session_refresher(self, refresher: Callable[[], None]) -> None:
        """Install a synchronized handshake refresh used only after auth rejection."""
        with self._identity_lock:
            self._session_refresher = refresher

    def _v2_lease_manager(self) -> LeaseClientManager | None:
        """Return the connected manager, if authenticated v2 is available."""

        with self._identity_lock:
            manager = self._lease_manager
        if manager is None or not manager.connected:
            return None
        return manager

    def _build_v2_context(
        self,
        *,
        document_names: Iterable[str] = (),
        selectors: Iterable[Mapping[str, Any]] = (),
        operation_name: str,
        task_id: str = "",
        request_id: str | None = None,
        require_credentials: bool = True,
    ) -> RpcRequestContext | None:
        """Resolve all declared documents once and freeze one request context.

        ``None`` means the connection has no authenticated v2 manager and the
        caller should use its compatibility RPC route.  Once v2 is connected,
        incomplete or conflicting document scope fails locally instead of
        silently falling back to a credential-less mutation.
        """

        manager = self._v2_lease_manager()
        if manager is None:
            return None
        with self._identity_lock:
            resolver = self._document_session_resolver

        session_ids: list[str] = []

        def add_session(session_uuid: str) -> None:
            if session_uuid and session_uuid not in session_ids:
                session_ids.append(session_uuid)

        for raw_name in document_names:
            name = str(raw_name or "")
            if not name:
                continue
            session_uuid = resolver(name) if resolver is not None else None
            if not session_uuid:
                raise LeaseNotFoundError(
                    f"no active lease credential is mapped to document {name!r}"
                )
            add_session(session_uuid)

        for raw_selector in selectors:
            selector = dict(raw_selector or {})
            selected_uuid = str(selector.get("document_session_uuid") or "")
            selected_name = str(selector.get("document_name") or "")
            selected_path = str(selector.get("canonical_path") or "")

            name_uuid = (
                resolver(selected_name)
                if selected_name and resolver is not None
                else None
            )
            if (
                selected_name
                and not name_uuid
                and not selected_uuid
                and not selected_path
            ):
                raise LeaseNotFoundError(
                    f"no active lease credential is mapped to document {selected_name!r}"
                )
            if selected_uuid and name_uuid and selected_uuid != name_uuid:
                raise LeaseNotFoundError(
                    "selector document name and session UUID identify different leases"
                )

            credential = None
            if selected_uuid or selected_path:
                credential = manager.get(
                    document_session_uuid=selected_uuid or None,
                    canonical_path=selected_path or None,
                )
                if credential is None:
                    raise LeaseNotFoundError(
                        "selector does not identify an active lease credential"
                    )
            elif name_uuid:
                credential = manager.get(document_session_uuid=name_uuid)
            if credential is not None:
                add_session(credential.document_session_uuid)

        if require_credentials and not session_ids:
            raise LeaseNotFoundError(
                f"authenticated mutation {operation_name!r} has no declared leased document"
            )
        return manager.build_request_context(
            document_session_uuids=session_ids,
            operation_name=operation_name,
            task_id=task_id,
            request_id=request_id,
        )

    def _unwrap_v2_response(
        self,
        response: Mapping[str, Any],
        *,
        additional_secrets: Iterable[str] = (),
    ) -> dict[str, Any]:
        """Restore the legacy method-result shape without losing diagnostics."""

        if not isinstance(response, Mapping):
            raise RuntimeError("Invalid invoke_v2 response type")
        result = response.get("result")
        if isinstance(result, Mapping):
            # The inner RPC method owns success/error semantics.  This is also
            # how validation and save failures remain structured when the
            # outer envelope has ``ok=false``.
            unwrapped = dict(result)
            for key in ("request_id", "addon_runtime_id", "leases"):
                if key in response:
                    unwrapped.setdefault(key, response[key])
            with self._identity_lock:
                manager = self._lease_manager
            if manager is not None:
                return manager.redact_value(
                    unwrapped, additional_secrets=additional_secrets
                )
            return unwrapped
        error = response.get("error")
        if isinstance(error, Mapping):
            unwrapped = {
                "success": False,
                "error_code": str(error.get("code") or "RPC_V2_ERROR"),
                "error": str(error.get("message") or "Authenticated RPC failed"),
                "request_id": str(response.get("request_id") or ""),
            }
            with self._identity_lock:
                manager = self._lease_manager
            if manager is not None:
                return manager.redact_value(
                    unwrapped, additional_secrets=additional_secrets
                )
            return unwrapped
        if response.get("ok") is False:
            return {
                "success": False,
                "error_code": "RPC_V2_ERROR",
                "error": "Authenticated RPC failed without a structured error",
                "request_id": str(response.get("request_id") or ""),
            }
        if result is None:
            return {"success": True}
        raise RuntimeError("Invalid invoke_v2 method result type")

    def _invoke_mutation_v2(
        self,
        method: str,
        params: Mapping[str, Any],
        *,
        document_names: Iterable[str] = (),
        selectors: Iterable[Mapping[str, Any]] = (),
        operation_name: str | None = None,
        task_id: str = "",
        request_id: str | None = None,
        require_credentials: bool = True,
        timeout: float | None = None,
    ) -> dict[str, Any] | None:
        """Invoke an authenticated mutation, or signal compatibility fallback."""

        if request_id is None:
            try:
                from mcp.server.lowlevel.server import request_ctx

                mcp_request_id = str(request_ctx.get().request_id)
            except (ImportError, LookupError, AttributeError):
                mcp_request_id = ""
            if mcp_request_id:
                try:
                    fingerprint_input = json.dumps(
                        {"method": method, "params": dict(params)},
                        ensure_ascii=True,
                        allow_nan=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                except (TypeError, ValueError):
                    fingerprint_input = repr((method, dict(params))).encode(
                        "utf-8", errors="replace"
                    )
                call_fingerprint = hashlib.sha256(fingerprint_input).hexdigest()
                request_id = str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        (
                            f"freecad-mcp:{self._mcp_instance_id}:"
                            f"{mcp_request_id}:{call_fingerprint}"
                        ),
                    )
                )

        context = self._build_v2_context(
            document_names=document_names,
            selectors=selectors,
            operation_name=operation_name or method,
            task_id=task_id,
            request_id=request_id,
            require_credentials=require_credentials,
        )
        if context is None:
            return None
        response = self.invoke_v2(method, params, context, timeout=timeout)
        return self._unwrap_v2_response(
            response,
            additional_secrets=(
                context.session_token,
                *(item.token for item in context.lease_credentials),
            ),
        )

    def set_identity(
        self,
        *,
        instance_id: str | None = None,
        client: str | None = None,
        pid: int | None = None,
        host: str | None = None,
    ) -> None:
        with self._identity_lock:
            if instance_id is not None:
                self._mcp_instance_id = instance_id
            if client is not None:
                self._mcp_client = client
            if pid is not None:
                self._mcp_pid = pid
            if host is not None:
                self._mcp_host = host
            self._refresh_headers()

    def set_active_lease_token(self, token: str | None) -> None:
        """Set the deprecated lease header for the current execution context.

        This API remains for v1 heartbeat/release callers. It no longer mutates
        shared connection state, so two threads cannot route one document's
        token onto another document's request.
        """

        self._legacy_lease_token.set(token)

    def _make_proxy(self, timeout: float) -> _ProxyLane:
        # Reuse the serialized general lane for the normal timeout. Longer
        # calls get an independent lane and cannot corrupt its transport.
        if timeout == self._timeout:
            return self.server
        return _ProxyLane(
            self._uri,
            timeout,
            self._request_headers_snapshot,
        )

    def invoke_rpc(
        self,
        method: str,
        *args: Any,
        control: bool = False,
        timeout: float | None = None,
    ) -> Any:
        """Invoke a method on a serialized general or independent control lane."""

        with self._identity_lock:
            if self._disconnected:
                raise RuntimeError("FreeCAD RPC connection is disconnected")
        if timeout is not None and timeout != self._timeout and not control:
            lane = self._make_proxy(timeout)
            try:
                return lane.call(method, *args)
            finally:
                lane.close()
        lane = self.control_server if control else self.server
        return lane.call(method, *args)

    def invoke_v2(
        self,
        method: str,
        params: Mapping[str, Any] | None,
        context: RpcRequestContext,
        *,
        control: bool = False,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Send one immutable v2 envelope without shared credential headers."""

        wire_params = _sign_generated_execute_params(method, params, context)
        envelope = context.to_envelope(method, wire_params)
        transport_method = "invoke_v2_control" if control else "invoke_v2"
        try:
            response = self.invoke_rpc(
                transport_method,
                envelope,
                control=control,
                timeout=timeout,
            )
        except Exception as exc:
            raise RpcInvocationError(method, exc) from None
        error = response.get("error") if isinstance(response, Mapping) else None
        error_code = error.get("code") if isinstance(error, Mapping) else None
        if error_code not in {"SESSION_EXPIRED", "UNKNOWN_SESSION"}:
            return response
        with self._identity_lock:
            refresher = self._session_refresher
            manager = self._lease_manager
        if refresher is None or manager is None:
            return response
        # An explicit auth rejection occurs before dispatch, so one retry is
        # safe. Preserve the request ID and document credentials while binding
        # the envelope to the newly negotiated session token.
        try:
            refresher()
        except Exception as exc:
            raise RpcInvocationError(method, exc) from None
        refreshed = manager.build_request_context(
            document_session_uuids=tuple(
                item.document_session_uuid for item in context.lease_credentials
            ),
            operation_name=context.operation_name,
            task_id=context.task_id,
            request_id=context.request_id,
        )
        try:
            refreshed_params = _sign_generated_execute_params(
                method, params, refreshed
            )
            return self.invoke_rpc(
                transport_method,
                refreshed.to_envelope(method, refreshed_params),
                control=control,
                timeout=timeout,
            )
        except Exception as exc:
            raise RpcInvocationError(method, exc) from None

    def heartbeat_document_locks_batch(
        self,
        payload: Mapping[str, Any],
        context: RpcRequestContext,
    ) -> dict[str, Any]:
        """Renew leases through the dedicated control transport."""

        return self.invoke_v2(
            "lease_heartbeat_batch",
            payload,
            context,
            control=True,
        )

    def reconcile_document_lease(
        self,
        document_session_uuid: str,
        *,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """Attempt exact-owner stale reconciliation on the control lane."""

        manager = self._v2_lease_manager()
        if manager is None:
            return {
                "success": False,
                "error_code": "LEASE_PROTOCOL_REQUIRED",
                "error": "Lease reconciliation requires authenticated RPC v2",
            }
        credential = manager.require(document_session_uuid=document_session_uuid)
        scoped = manager.build_request_context(
            document_session_uuids=(document_session_uuid,),
            operation_name="Reconcile stale document lease",
            request_id=request_id,
        )
        response = self.invoke_v2(
            "lease_reconcile",
            {"credential": credential.to_wire()},
            scoped,
            control=True,
        )
        return self._unwrap_v2_response(
            response,
            additional_secrets=(scoped.session_token, credential.token),
        )

    def get_request_status(
        self,
        target_request_id: str,
        *,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """Query completion after a timeout without replaying the mutation."""

        try:
            parsed_target_request_id = uuid.UUID(str(target_request_id))
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError("target_request_id must be a UUID") from exc
        if parsed_target_request_id.int == 0:
            raise ValueError("target_request_id must not be the nil UUID")
        target_request_id = str(parsed_target_request_id)
        context = self._build_v2_context(
            operation_name="Get request status",
            request_id=request_id,
            require_credentials=False,
        )
        if context is None:
            return {
                "success": False,
                "error_code": "LEASE_PROTOCOL_REQUIRED",
                "error": "Request status requires authenticated RPC v2",
            }
        response = self.invoke_v2(
            "get_request_status",
            {"request_id": target_request_id},
            context,
            control=True,
        )
        return self._unwrap_v2_response(
            response,
            additional_secrets=(context.session_token,),
        )

    def cancel_request(
        self,
        target_request_id: str,
        *,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """Cancel an owned v2 request through the reserved control lane.

        This low-level recovery primitive is intentionally not exposed as a
        model-facing MCP tool.
        """

        try:
            parsed_target_request_id = uuid.UUID(str(target_request_id))
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError("target_request_id must be a UUID") from exc
        if parsed_target_request_id.int == 0:
            raise ValueError("target_request_id must not be the nil UUID")
        target_request_id = str(parsed_target_request_id)
        context = self._build_v2_context(
            operation_name="Cancel request",
            request_id=request_id,
            require_credentials=False,
        )
        if context is None:
            return {
                "success": False,
                "error_code": "LEASE_PROTOCOL_REQUIRED",
                "error": "Request cancellation requires authenticated RPC v2",
            }
        response = self.invoke_v2(
            "cancel_request",
            {"target_request_id": target_request_id},
            context,
            control=True,
        )
        return self._unwrap_v2_response(
            response,
            additional_secrets=(context.session_token,),
        )

    def disconnect(self) -> None:
        """Close both lanes. Lease release remains an explicit lifecycle step."""

        with self._identity_lock:
            if self._disconnected:
                return
            self._disconnected = True
            manager = self._lease_manager
            self._session_refresher = None
        if manager is not None:
            manager.mark_disconnected("FreeCAD RPC connection disconnected")
        token_var = getattr(self, "_legacy_lease_token", None)
        if token_var is not None:
            token_var.set(None)
        seen: set[int] = set()
        first_error: BaseException | None = None
        for lane in (
            getattr(self, "server", None),
            getattr(self, "control_server", None),
        ):
            if lane is None or id(lane) in seen:
                continue
            seen.add(id(lane))
            close = getattr(lane, "close", None)
            if callable(close):
                try:
                    close()
                except Exception as exc:
                    if first_error is None:
                        first_error = exc
                continue
            # Supports tests/legacy callers that replace ``server`` with a raw
            # ServerProxy or MagicMock after construction.
            transport = getattr(lane, "_ServerProxy__transport", None)
            close_transport = getattr(transport, "close", None)
            if callable(close_transport):
                try:
                    close_transport()
                except Exception as exc:
                    if first_error is None:
                        first_error = exc
        if first_error is not None:
            raise RpcInvocationError("disconnect", first_error) from None

    def ping(self) -> bool:
        return self.server.ping()

    def check_rpc_sync(self, nonce: str) -> dict[str, Any]:
        return self.server.check_rpc_sync(nonce)

    def get_instance_info(self) -> dict[str, Any]:
        """Identity of the FreeCAD addon answering on this port."""
        return self.server.get_instance_info()

    def verify_instance(self) -> dict[str, Any]:
        """Confirm the addon on this port is the expected instance.

        No-op (returns the reported info) when no ``expected_instance_id`` was
        configured. Raises ``InstanceMismatchError`` when the id differs, so a
        client configured for an isolated instance never silently drives the
        wrong FreeCAD when several addons listen on nearby ports.
        """
        info = self.get_instance_info()
        if not self._expected_instance_id:
            return info
        actual = (info or {}).get("instance_id")
        if actual != self._expected_instance_id:
            raise InstanceMismatchError(
                f"Expected FreeCAD instance '{self._expected_instance_id}' on "
                f"{self._uri} but the addon reported '{actual}'. Refusing to "
                "drive the wrong instance."
            )
        return info

    def create_document(
        self, name: str, *, request_id: str | None = None
    ) -> dict[str, Any]:
        routed = self._invoke_mutation_v2(
            "create_document",
            {"name": name},
            operation_name="Create document",
            request_id=request_id,
            require_credentials=False,
        )
        if routed is not None:
            return routed
        return self.server.create_document(name)

    def create_object(self, doc_name: str, obj_data: dict[str, Any]) -> dict[str, Any]:
        routed = self._invoke_mutation_v2(
            "create_object",
            {"doc_name": doc_name, "obj_data": obj_data},
            document_names=(doc_name,),
            operation_name="Create object",
        )
        if routed is not None:
            return routed
        return self.server.create_object(doc_name, obj_data)

    def edit_object(
        self, doc_name: str, obj_name: str, obj_data: dict[str, Any]
    ) -> dict[str, Any]:
        routed = self._invoke_mutation_v2(
            "edit_object",
            {"doc_name": doc_name, "obj_name": obj_name, "properties": obj_data},
            document_names=(doc_name,),
            operation_name="Edit object",
        )
        if routed is not None:
            return routed
        return self.server.edit_object(doc_name, obj_name, obj_data)

    def inspect_references(
        self,
        doc_name: str,
        object_names: list[str] | None = None,
        only_invalid: bool = False,
        validate: bool = False,
    ) -> dict[str, Any]:
        return self.server.inspect_references(
            doc_name, object_names, only_invalid, validate
        )

    def repair_references(
        self,
        doc_name: str,
        repairs: list[dict[str, Any]],
        recompute: bool = False,
        validate: bool = False,
    ) -> dict[str, Any]:
        routed = self._invoke_mutation_v2(
            "repair_references",
            {
                "doc_name": doc_name,
                "repairs": repairs,
                "recompute": recompute,
                "validate": validate,
            },
            document_names=(doc_name,),
            operation_name="Repair references",
        )
        if routed is not None:
            return routed
        return self.server.repair_references(doc_name, repairs, recompute, validate)

    def delete_object(self, doc_name: str, obj_name: str) -> dict[str, Any]:
        routed = self._invoke_mutation_v2(
            "delete_object",
            {"doc_name": doc_name, "obj_name": obj_name},
            document_names=(doc_name,),
            operation_name="Delete object",
        )
        if routed is not None:
            return routed
        return self.server.delete_object(doc_name, obj_name)

    def reload_document(self, doc_name: str) -> dict[str, Any]:
        routed = self._invoke_mutation_v2(
            "reload_document",
            {"doc_name": doc_name},
            document_names=(doc_name,),
            operation_name="Reload document",
        )
        if routed is not None:
            return routed
        return self.server.reload_document(doc_name)

    def insert_part_from_library(
        self, doc_name: str, relative_path: str
    ) -> dict[str, Any]:
        routed = self._invoke_mutation_v2(
            "insert_part_from_library",
            {"doc_name": doc_name, "relative_path": relative_path},
            document_names=(doc_name,),
            operation_name="Insert part from library",
        )
        if routed is not None:
            return routed
        return self.server.insert_part_from_library(doc_name, relative_path)

    def execute_code(
        self,
        code: str,
        options: dict[str, Any] | ExecuteOptions | None = None,
        *,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        opts = (
            options.to_dict()
            if isinstance(options, ExecuteOptions)
            else (options or {})
        )
        # Snapshot reads deliberately stay on the ordinary RPC route.  Every
        # live mutation in an authenticated session carries one immutable
        # request id and the exact credentials for the complete declared
        # scope.  Generated operations use their audited operation id in the
        # attribution context.
        if not bool(opts.get("read_only", False)):
            primary = str(opts.get("document") or "")
            raw_affected = opts.get("affected_documents") or ()
            if isinstance(raw_affected, (str, bytes)):
                raise ValueError("affected_documents must be a list of document names")
            affected = []
            for name in raw_affected:
                if not isinstance(name, str) or not name:
                    raise ValueError(
                        "affected_documents entries must be non-empty strings"
                    )
                affected.append(name)
            document_names = []
            if primary:
                document_names.append(primary)
            for name in affected:
                if name not in document_names:
                    document_names.append(name)
            operation_id = str(opts.get("operation_id") or "")
            routed = self._invoke_mutation_v2(
                "execute_code",
                {"code": code, "options": dict(opts)},
                document_names=document_names,
                operation_name=operation_id or "execute_code",
                task_id=operation_id,
                request_id=request_id,
            )
            if routed is not None:
                return routed
        return self.server.execute_code(code, opts)

    def get_worker_status(self) -> dict[str, Any]:
        return self.server.get_worker_status()

    def cancel_worker_job(self, job_id: str) -> dict[str, Any]:
        return self.server.cancel_worker_job(job_id)

    def execute_code_async(self, code: str) -> dict[str, Any]:
        if self._v2_lease_manager() is not None:
            return {
                "success": False,
                "error_code": "EXECUTE_CODE_ASYNC_DISABLED",
                "error": (
                    "Live execute_code_async is disabled for authenticated lease "
                    "sessions; use scoped execute_code so completion is attributable"
                ),
            }
        return self.server.execute_code_async(code)

    def get_active_screenshot(
        self,
        view_name: str | None = "Isometric",
        width: int | None = None,
        height: int | None = None,
        focus_object: str | None = None,
        focus_objects: list[str] | None = None,
        yaw_deg: float | None = None,
    ) -> str | None:
        try:
            return self.server.get_active_screenshot(
                view_name,
                width,
                height,
                focus_object,
                focus_objects,
                yaw_deg,
            )
        except Exception as e:
            logger.error(f"Error getting screenshot: {e}")
            return None

    def capture_view_sequence(
        self,
        frames: list[dict[str, Any]] | None = None,
        width: int | None = None,
        height: int | None = None,
        orbit: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            return self.server.capture_view_sequence(frames, width, height, orbit)
        except Exception as e:
            logger.error(f"Error capturing view sequence: {e}")
            return {"ok": False, "error": str(e), "frames": []}

    def capture_view_sequence_to_disk(
        self,
        frames: list[dict[str, Any]] | None = None,
        width: int | None = None,
        height: int | None = None,
        orbit: dict[str, Any] | None = None,
        frame_dir: str | None = None,
    ) -> dict[str, Any]:
        try:
            return self.server.capture_view_sequence_to_disk(
                frames, width, height, orbit, frame_dir
            )
        except Exception as e:
            logger.error(f"Error capturing view sequence to disk: {e}")
            return {"ok": False, "error": str(e), "frame_paths": []}

    def refresh_view(
        self,
        focus_objects: list[str] | None = None,
        focus_object: str | None = None,
        touch_objects: list[str] | None = None,
        fit: bool = False,
        capture: bool = False,
        view_name: str = "Isometric",
        width: int | None = None,
        height: int | None = None,
    ) -> dict[str, Any]:
        try:
            return self.server.refresh_view(
                focus_objects,
                focus_object,
                touch_objects,
                fit,
                capture,
                view_name,
                width,
                height,
            )
        except Exception as e:
            logger.error(f"Error refreshing view: {e}")
            return {"ok": False, "error": str(e)}

    def repair_view_placements(
        self, doc_name: str, touch_objects: list[str], fit: bool = False
    ) -> dict[str, Any]:
        routed = self._invoke_mutation_v2(
            "repair_view_placements",
            {
                "doc_name": doc_name,
                "touch_objects": touch_objects,
                "fit": fit,
            },
            document_names=(doc_name,),
            operation_name="Repair view placements",
        )
        if routed is not None:
            return routed
        return self.server.repair_view_placements(doc_name, touch_objects, fit)

    def animate_placement(
        self,
        doc_name: str,
        obj_name: str,
        keyframes: list[dict[str, Any]] | None = None,
        path_object: str | None = None,
        sample_count: int = 12,
        view_name: str = "Isometric",
        focus_objects: list[str] | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> dict[str, Any]:
        try:
            routed = self._invoke_mutation_v2(
                "animate_placement",
                {
                    "doc_name": doc_name,
                    "obj_name": obj_name,
                    "keyframes": keyframes,
                    "path_object": path_object,
                    "sample_count": sample_count,
                    "view_name": view_name,
                    "focus_objects": focus_objects,
                    "width": width,
                    "height": height,
                },
                document_names=(doc_name,),
                operation_name="Animate placement",
            )
            if routed is not None:
                return routed
            return self.server.animate_placement(
                doc_name,
                obj_name,
                keyframes,
                path_object,
                sample_count,
                view_name,
                focus_objects,
                width,
                height,
            )
        except Exception as e:
            logger.error(f"Error animating placement: {e}")
            return {"ok": False, "error": str(e)}

    def get_objects(self, doc_name: str) -> list[dict[str, Any]]:
        return self.server.get_objects(doc_name)

    def get_object(self, doc_name: str, obj_name: str) -> dict[str, Any]:
        return self.server.get_object(doc_name, obj_name)

    def get_parts_list(self) -> list[str]:
        return self.server.get_parts_list()

    def list_documents(self) -> list[str]:
        return self.server.list_documents()

    def open_document(self, path: str) -> dict[str, Any]:
        return self.server.open_document(path)

    def activate_document(self, doc_name: str) -> dict[str, Any]:
        return self.server.activate_document(doc_name)

    def set_tree_expanded(
        self,
        doc_name: str,
        object_names: list[str] | None = None,
        mode: str = "expand",
    ) -> dict[str, Any]:
        return self.server.set_tree_expanded(doc_name, object_names, mode)

    def select_subshapes(
        self,
        doc_name: str,
        selections: list | None = None,
        clear: bool = True,
    ) -> dict[str, Any]:
        return self.server.select_subshapes(doc_name, selections, clear)

    def get_selection(self) -> dict[str, Any]:
        return self.server.get_selection()

    def get_gui_state(self) -> dict[str, Any]:
        return self.server.get_gui_state()

    def recompute_and_wait(self, doc_name: str) -> dict[str, Any]:
        routed = self._invoke_mutation_v2(
            "recompute_and_wait",
            {"doc_name": doc_name},
            document_names=(doc_name,),
            operation_name="Recompute document",
        )
        if routed is not None:
            return routed
        return self.server.recompute_and_wait(doc_name)

    def set_section_view(
        self,
        enabled: bool | None = None,
        placement: dict[str, Any] | None = None,
        base: list[float] | None = None,
        normal: list[float] | None = None,
        no_manip: bool = True,
    ) -> dict[str, Any]:
        return self.server.set_section_view(enabled, placement, base, normal, no_manip)

    def sketch_create(
        self,
        doc_name: str,
        sketch_name: str,
        body_name: str | None = None,
        attach_to: str | None = None,
    ) -> dict[str, Any]:
        routed = self._invoke_mutation_v2(
            "sketch_create",
            {
                "doc_name": doc_name,
                "sketch_name": sketch_name,
                "body_name": body_name,
                "attach_to": attach_to,
            },
            document_names=(doc_name,),
            operation_name="Create sketch",
        )
        if routed is not None:
            return routed
        return self.server.sketch_create(doc_name, sketch_name, body_name, attach_to)

    def sketch_add_geometry(
        self, doc_name: str, sketch_name: str, geometry: list
    ) -> dict[str, Any]:
        routed = self._invoke_mutation_v2(
            "sketch_add_geometry",
            {"doc_name": doc_name, "sketch_name": sketch_name, "geometry": geometry},
            document_names=(doc_name,),
            operation_name="Add sketch geometry",
        )
        if routed is not None:
            return routed
        return self.server.sketch_add_geometry(doc_name, sketch_name, geometry)

    def sketch_add_constraint(
        self, doc_name: str, sketch_name: str, constraints: list
    ) -> dict[str, Any]:
        routed = self._invoke_mutation_v2(
            "sketch_add_constraint",
            {
                "doc_name": doc_name,
                "sketch_name": sketch_name,
                "constraints": constraints,
            },
            document_names=(doc_name,),
            operation_name="Add sketch constraint",
        )
        if routed is not None:
            return routed
        return self.server.sketch_add_constraint(doc_name, sketch_name, constraints)

    def pad_feature(
        self,
        doc_name: str,
        sketch_name: str,
        pad_name: str,
        length: float,
        body_name: str | None = None,
        symmetric: bool = False,
        reversed_dir: bool = False,
    ) -> dict[str, Any]:
        routed = self._invoke_mutation_v2(
            "pad_feature",
            {
                "doc_name": doc_name,
                "sketch_name": sketch_name,
                "pad_name": pad_name,
                "length": length,
                "body_name": body_name,
                "symmetric": symmetric,
                "reversed_dir": reversed_dir,
            },
            document_names=(doc_name,),
            operation_name="Create Pad",
        )
        if routed is not None:
            return routed
        return self.server.pad_feature(
            doc_name, sketch_name, pad_name, length, body_name, symmetric, reversed_dir
        )

    def pocket_feature(
        self,
        doc_name: str,
        sketch_name: str,
        pocket_name: str,
        length: float,
        body_name: str | None = None,
        symmetric: bool = False,
        reversed_dir: bool = False,
    ) -> dict[str, Any]:
        routed = self._invoke_mutation_v2(
            "pocket_feature",
            {
                "doc_name": doc_name,
                "sketch_name": sketch_name,
                "pocket_name": pocket_name,
                "length": length,
                "body_name": body_name,
                "symmetric": symmetric,
                "reversed_dir": reversed_dir,
            },
            document_names=(doc_name,),
            operation_name="Create Pocket",
        )
        if routed is not None:
            return routed
        return self.server.pocket_feature(
            doc_name,
            sketch_name,
            pocket_name,
            length,
            body_name,
            symmetric,
            reversed_dir,
        )

    def spreadsheet_create(self, doc_name: str, sheet_name: str) -> dict[str, Any]:
        routed = self._invoke_mutation_v2(
            "spreadsheet_create",
            {"doc_name": doc_name, "sheet_name": sheet_name},
            document_names=(doc_name,),
            operation_name="Create spreadsheet",
        )
        if routed is not None:
            return routed
        return self.server.spreadsheet_create(doc_name, sheet_name)

    def spreadsheet_set_cells(
        self, doc_name: str, sheet_name: str, cells: list
    ) -> dict[str, Any]:
        routed = self._invoke_mutation_v2(
            "spreadsheet_set_cells",
            {"doc_name": doc_name, "sheet_name": sheet_name, "cells": cells},
            document_names=(doc_name,),
            operation_name="Set spreadsheet cells",
        )
        if routed is not None:
            return routed
        return self.server.spreadsheet_set_cells(doc_name, sheet_name, cells)

    def spreadsheet_get_cells(
        self, doc_name: str, sheet_name: str, addresses: list
    ) -> dict[str, Any]:
        return self.server.spreadsheet_get_cells(doc_name, sheet_name, addresses)

    def spreadsheet_set_alias(
        self, doc_name: str, sheet_name: str, address: str, alias: str
    ) -> dict[str, Any]:
        routed = self._invoke_mutation_v2(
            "spreadsheet_set_alias",
            {
                "doc_name": doc_name,
                "sheet_name": sheet_name,
                "address": address,
                "alias": alias,
            },
            document_names=(doc_name,),
            operation_name="Set spreadsheet alias",
        )
        if routed is not None:
            return routed
        return self.server.spreadsheet_set_alias(doc_name, sheet_name, address, alias)

    def spreadsheet_list_aliases(
        self, doc_name: str, sheet_name: str
    ) -> dict[str, Any]:
        return self.server.spreadsheet_list_aliases(doc_name, sheet_name)

    def set_expression(
        self, doc_name: str, object_name: str, prop_path: str, expression: str
    ) -> dict[str, Any]:
        routed = self._invoke_mutation_v2(
            "set_expression",
            {
                "doc_name": doc_name,
                "object_name": object_name,
                "prop_path": prop_path,
                "expression": expression,
            },
            document_names=(doc_name,),
            operation_name="Set expression",
        )
        if routed is not None:
            return routed
        return self.server.set_expression(doc_name, object_name, prop_path, expression)

    def clear_expression(
        self, doc_name: str, object_name: str, prop_path: str
    ) -> dict[str, Any]:
        routed = self._invoke_mutation_v2(
            "clear_expression",
            {"doc_name": doc_name, "object_name": object_name, "prop_path": prop_path},
            document_names=(doc_name,),
            operation_name="Clear expression",
        )
        if routed is not None:
            return routed
        return self.server.clear_expression(doc_name, object_name, prop_path)

    def list_expressions(self, doc_name: str, object_name: str) -> dict[str, Any]:
        return self.server.list_expressions(doc_name, object_name)

    def body_create(self, doc_name: str, body_name: str) -> dict[str, Any]:
        routed = self._invoke_mutation_v2(
            "body_create",
            {"doc_name": doc_name, "body_name": body_name},
            document_names=(doc_name,),
            operation_name="Create Body",
        )
        if routed is not None:
            return routed
        return self.server.body_create(doc_name, body_name)

    def body_set_tip(
        self, doc_name: str, body_name: str, feature_name: str
    ) -> dict[str, Any]:
        routed = self._invoke_mutation_v2(
            "body_set_tip",
            {
                "doc_name": doc_name,
                "body_name": body_name,
                "feature_name": feature_name,
            },
            document_names=(doc_name,),
            operation_name="Set Body Tip",
        )
        if routed is not None:
            return routed
        return self.server.body_set_tip(doc_name, body_name, feature_name)

    def sketch_attach(self, doc_name: str, sketch_name: str, support) -> dict[str, Any]:
        routed = self._invoke_mutation_v2(
            "sketch_attach",
            {"doc_name": doc_name, "sketch_name": sketch_name, "support": support},
            document_names=(doc_name,),
            operation_name="Attach sketch",
        )
        if routed is not None:
            return routed
        return self.server.sketch_attach(doc_name, sketch_name, support)

    def sketch_edit_constraint(
        self,
        doc_name: str,
        sketch_name: str,
        value: float | None = None,
        name: str | None = None,
        index: int | None = None,
    ) -> dict[str, Any]:
        routed = self._invoke_mutation_v2(
            "sketch_edit_constraint",
            {
                "doc_name": doc_name,
                "sketch_name": sketch_name,
                "value": value,
                "name": name,
                "index": index,
            },
            document_names=(doc_name,),
            operation_name="Edit sketch constraint",
        )
        if routed is not None:
            return routed
        return self.server.sketch_edit_constraint(
            doc_name, sketch_name, value, name, index
        )

    def diagnose_parametric(
        self, doc_name: str, object_name: str | None = None
    ) -> dict[str, Any]:
        return self.server.diagnose_parametric(doc_name, object_name)

    def recompute_document(self, doc_name: str) -> dict[str, Any]:
        routed = self._invoke_mutation_v2(
            "recompute_document",
            {"doc_name": doc_name},
            document_names=(doc_name,),
            operation_name="Recompute document",
        )
        if routed is not None:
            return routed
        return self.server.recompute_document(doc_name)

    def undo(self, doc_name: str) -> dict[str, Any]:
        routed = self._invoke_mutation_v2(
            "undo",
            {"doc_name": doc_name},
            document_names=(doc_name,),
            operation_name="Undo",
        )
        if routed is not None:
            return routed
        return self.server.undo(doc_name)

    def redo(self, doc_name: str) -> dict[str, Any]:
        routed = self._invoke_mutation_v2(
            "redo",
            {"doc_name": doc_name},
            document_names=(doc_name,),
            operation_name="Redo",
        )
        if routed is not None:
            return routed
        return self.server.redo(doc_name)

    def run_fem_analysis(
        self, doc_name: str, analysis_name: str, timeout: int = 600
    ) -> dict[str, Any]:
        # The solver blocks the RPC response for up to `timeout` seconds, so the
        # socket must outlast it. The default 150 s transport timeout would abort
        # any solve longer than that even though the addon is still working.
        # Use a dedicated proxy whose socket timeout exceeds the solver timeout.
        rpc_timeout = max(self._timeout, timeout + 30)
        routed = self._invoke_mutation_v2(
            "run_fem_analysis",
            {
                "doc_name": doc_name,
                "analysis_name": analysis_name,
                "timeout": timeout,
            },
            document_names=(doc_name,),
            operation_name="Run FEM analysis",
            timeout=rpc_timeout,
        )
        if routed is not None:
            return routed
        proxy = self._make_proxy(rpc_timeout)
        try:
            return proxy.run_fem_analysis(doc_name, analysis_name, timeout)
        finally:
            if proxy is not self.server:
                proxy.close()

    # --- Document lock / lease -----------------------------------------------

    def acquire_document_lock(
        self,
        doc_name: str = "",
        file_path: str = "",
        session_id: str = "",
        task_description: str = "",
        client: str = "",
        selector: Mapping[str, Any] | None = None,
        agent_id: str = "",
        hash_policy: str = "sha256",
        request_id: str | None = None,
    ) -> dict[str, Any]:
        params = {
            "doc_name": doc_name,
            "file_path": file_path,
            "session_id": session_id,
            "task_description": task_description,
            "client": client,
            "selector": dict(selector or {}),
            "agent_id": agent_id,
            "hash_policy": hash_policy,
        }
        routed = self._invoke_mutation_v2(
            "acquire_document_lock",
            params,
            operation_name="Acquire document lease",
            task_id=agent_id,
            request_id=request_id,
            require_credentials=False,
        )
        if routed is not None:
            return routed
        return self.server.acquire_document_lock(
            doc_name,
            file_path,
            session_id,
            task_description,
            client,
            dict(selector or {}),
            agent_id,
            hash_policy,
        )

    def get_document_lock(
        self,
        doc_name: str = "",
        file_path: str = "",
        session_id: str = "",
        selector: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.server.get_document_lock(
            doc_name, file_path, session_id, dict(selector or {})
        )

    def list_document_locks(self) -> dict[str, Any]:
        return self.server.list_document_locks()

    def heartbeat_document_lock(
        self,
        doc_key: str,
        token: str,
        current_operation: str = "",
        state: str = "",
        document_dirty: bool | None = None,
    ) -> dict[str, Any]:
        return self.server.heartbeat_document_lock(
            doc_key, token, current_operation, state, document_dirty
        )

    def update_document_lock(
        self,
        selector: Mapping[str, Any],
        task_description: str = "",
        progress_detail: str = "",
        *,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        selected = dict(selector)
        routed = self._invoke_mutation_v2(
            "update_document_lock",
            {
                "selector": selected,
                "task_description": task_description,
                "progress_detail": progress_detail,
            },
            selectors=(selected,),
            operation_name="Update lease metadata",
            request_id=request_id,
        )
        if routed is not None:
            return routed
        return self.server.update_document_lock(
            selected, task_description, progress_detail
        )

    def save_document(
        self,
        selector: Mapping[str, Any],
        validation_profile: str = "default",
        *,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        selected = dict(selector)
        routed = self._invoke_mutation_v2(
            "save_document",
            {
                "selector": selected,
                "validation_profile": validation_profile,
            },
            selectors=(selected,),
            operation_name="Save and verify document",
            request_id=request_id,
        )
        if routed is not None:
            return routed
        return self.server.save_document(selected, validation_profile)

    def save_document_as(
        self,
        selector: Mapping[str, Any],
        destination: str,
        overwrite: bool = False,
        expected_destination_sha256: str = "",
        validation_profile: str = "default",
        *,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        selected = dict(selector)
        routed = self._invoke_mutation_v2(
            "save_document_as",
            {
                "selector": selected,
                "destination": destination,
                "overwrite": overwrite,
                "expected_destination_sha256": expected_destination_sha256,
                "validation_profile": validation_profile,
            },
            selectors=(selected,),
            operation_name="Save As and verify document",
            request_id=request_id,
        )
        if routed is not None:
            return routed
        return self.server.save_document_as(
            selected,
            destination,
            overwrite,
            expected_destination_sha256,
            validation_profile,
        )

    def finalize_document_edit(
        self,
        selector: Mapping[str, Any],
        save_mode: str = "save",
        destination: str = "",
        overwrite: bool = False,
        expected_destination_sha256: str = "",
        validation_profile: str = "default",
        *,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        selected = dict(selector)
        routed = self._invoke_mutation_v2(
            "finalize_document_edit",
            {
                "selector": selected,
                "save_mode": save_mode,
                "destination": destination,
                "overwrite": overwrite,
                "expected_destination_sha256": expected_destination_sha256,
                "validation_profile": validation_profile,
            },
            selectors=(selected,),
            operation_name="Finalize document edit",
            request_id=request_id,
        )
        if routed is not None:
            return routed
        return self.server.finalize_document_edit(
            selected,
            save_mode,
            destination,
            overwrite,
            expected_destination_sha256,
            validation_profile,
        )

    def release_document_lock(
        self,
        doc_key: str = "",
        token: str = "",
        *,
        selector: Mapping[str, Any] | None = None,
        disposition: str = "saved",
        request_id: str | None = None,
    ) -> dict[str, Any]:
        selected = None if selector is None else dict(selector)
        if selected is not None:
            routed = self._invoke_mutation_v2(
                "release_document_lock",
                {
                    "doc_key": doc_key,
                    "token": token,
                    "selector": selected,
                    "disposition": disposition,
                },
                selectors=(selected,),
                operation_name="Release document lease",
                request_id=request_id,
            )
            if routed is not None:
                return routed
        return self.server.release_document_lock(
            doc_key,
            token,
            selected,
            disposition,
        )

    def force_release_stale_lock(self, doc_key: str) -> dict[str, Any]:
        return self.server.force_release_stale_lock(doc_key)
