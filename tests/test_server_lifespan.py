import asyncio
import unittest
from unittest import mock
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from freecad_mcp import server
from freecad_mcp.lease_manager import LeaseClientManager, LeaseCredential


class ServerLifespanTest(unittest.TestCase):
    def setUp(self):
        self.state_patcher = mock.patch.object(server, "state", server.ServerState())
        self.state = self.state_patcher.start()
        self.addCleanup(self.state_patcher.stop)

    def test_startup_does_not_connect_to_freecad(self):
        async def run_lifespan():
            with mock.patch.object(
                server,
                "get_freecad_connection",
                side_effect=AssertionError("startup should not connect to FreeCAD"),
            ):
                async with server.server_lifespan(object()):
                    self.assertIsNone(server.state.freecad_connection)

        asyncio.run(run_lifespan())

    def test_get_freecad_connection_connects_lazily(self):
        connection = mock.Mock()
        connection.ping.return_value = True

        with mock.patch.object(
            server, "FreeCADConnection", return_value=connection
        ) as factory:
            result = server.get_freecad_connection()

        self.assertIs(result, connection)
        factory.assert_called_once_with(
            host="127.0.0.1",
            port=9875,
            expected_instance_id=None,
            mcp_instance_id=server.state.mcp_instance_id,
            mcp_client=server.state.mcp_client_label,
            mcp_pid=server.state.mcp_pid or None,
            mcp_host=server.state.mcp_host or None,
        )
        connection.ping.assert_called_once_with()

    def test_shutdown_disconnects_existing_connection(self):
        connection = mock.Mock()
        self.state.freecad_connection = connection
        self.state.lease_manager = LeaseClientManager(session_token="rpc-session")
        self.state.lease_manager.store(
            LeaseCredential(
                lease_id="lease-a",
                document_session_uuid="doc-a",
                generation=1,
                token="lease-secret",
            )
        )
        self.state.lease_tokens["legacy"] = "legacy-secret"
        self.state.document_sessions["Doc"] = "doc-a"
        self.state.rpc_session_id = "session-id"
        self.state.rpc_session_expires_at = "2099-01-01T00:00:00Z"
        self.state.authenticated_manifest = object()

        async def run_lifespan():
            async with server.server_lifespan(object()):
                self.assertIs(server.state.freecad_connection, connection)

        asyncio.run(run_lifespan())

        connection.disconnect.assert_called_once_with()
        self.assertIsNone(server.state.freecad_connection)
        self.assertTrue(server.state.lease_manager.redacted_status()["closed"])
        self.assertEqual(server.state.lease_tokens, {})
        self.assertEqual(server.state.document_sessions, {})
        self.assertIsNone(server.state.rpc_session_id)
        self.assertIsNone(server.state.rpc_session_expires_at)
        self.assertIsNone(server.state.authenticated_manifest)

    def test_connection_initialization_failure_closes_transport_and_fences_session(
        self,
    ):
        connection = mock.Mock()
        connection.ping.return_value = False
        self.state.lease_manager = LeaseClientManager(session_token="old-session")

        with (
            mock.patch.object(server, "FreeCADConnection", return_value=connection),
            self.assertRaisesRegex(Exception, "Failed to connect"),
        ):
            server.get_freecad_connection()

        connection.disconnect.assert_called_once_with()
        self.assertIsNone(server.state.freecad_connection)
        self.assertFalse(server.state.lease_manager.connected)

    def test_shutdown_clears_sensitive_state_even_when_transport_close_fails(self):
        connection = mock.Mock()
        connection.disconnect.side_effect = RuntimeError("remote echoed legacy-secret")
        self.state.freecad_connection = connection
        self.state.lease_tokens["legacy"] = "legacy-secret"
        self.state.document_sessions["Doc"] = "doc-a"

        async def run_lifespan():
            with mock.patch.object(server.logger, "warning") as warning:
                async with server.server_lifespan(object()):
                    pass
                self.assertNotIn("legacy-secret", repr(warning.call_args_list))

        asyncio.run(run_lifespan())

        self.assertIsNone(self.state.freecad_connection)
        self.assertEqual(self.state.lease_tokens, {})
        self.assertEqual(self.state.document_sessions, {})

    def test_session_refresh_margin_is_fail_closed(self):
        now = datetime.now(timezone.utc)
        self.state.rpc_session_expires_at = (now + timedelta(minutes=10)).isoformat()
        self.assertFalse(server._session_needs_refresh())

        self.state.rpc_session_expires_at = (now + timedelta(seconds=30)).isoformat()
        self.assertTrue(server._session_needs_refresh())

        self.state.rpc_session_expires_at = "not-a-timestamp"
        self.assertTrue(server._session_needs_refresh())

    def test_authenticated_session_refresh_preserves_held_lease_credentials(self):
        expiry = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        manifest = SimpleNamespace(auth_secret_file="profile.auth")
        verified = SimpleNamespace(
            session_token="new-session",
            session_id="new-session-id",
            session_expires_at=expiry,
            manifest=SimpleNamespace(addon_runtime_id="addon-runtime"),
        )
        connection = mock.Mock()
        connection.invoke_rpc.return_value = {"signed": "response"}
        self.state.instance_manifest = manifest
        self.state.lease_manager = LeaseClientManager(session_token="old-session")
        credential = LeaseCredential(
            lease_id="lease-a",
            document_session_uuid="doc-a",
            generation=3,
            token="lease-secret",
        )
        self.state.lease_manager.store(credential)

        with (
            mock.patch.object(server, "load_profile_secret", return_value=b"x" * 32),
            mock.patch.object(
                server, "make_mcp_runtime_identity", return_value=object()
            ),
            mock.patch.object(
                server,
                "build_handshake_request_from_manifest",
                return_value={"client_nonce": "nonce"},
            ),
            mock.patch.object(
                server,
                "verify_handshake_response_from_manifest",
                return_value=verified,
            ),
        ):
            server._authenticate_connection(connection, force=True)

        self.assertTrue(self.state.lease_manager.connected)
        self.assertIs(
            self.state.lease_manager.get(document_session_uuid="doc-a"), credential
        )
        self.assertEqual(self.state.rpc_session_id, "new-session-id")
        self.assertEqual(self.state.rpc_session_expires_at, expiry)
        connection.configure_lease_routing.assert_called_once()
        connection.configure_session_refresher.assert_called_once()

    def test_session_refresh_reloads_launcher_authorized_runtime_manifest(self):
        manifest_path = "C:/isolated-profile/instance-manifest.json"

        def manifest(runtime_id, pid, build_id):
            return SimpleNamespace(
                schema_version=1,
                profile_instance_id="profile-a",
                profile_path="C:/isolated-profile",
                auth_secret_file="C:/isolated-profile/auth.secret",
                rpc_host="127.0.0.1",
                rpc_port=19876,
                expected_profile_path_fingerprint="profile-fingerprint-a",
                created_at="2026-07-22T00:00:00Z",
                expected_addon_runtime_id=runtime_id,
                expected_freecad_pid=pid,
                expected_addon_build_id=build_id,
                require_complete_runtime=mock.Mock(),
            )

        original = manifest("runtime-old", 1001, "build-old")
        refreshed = manifest("runtime-new", 2002, "build-new")
        expiry = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        verified = SimpleNamespace(
            session_token="new-session-token",
            session_id="new-session-id",
            session_expires_at=expiry,
            manifest=SimpleNamespace(addon_runtime_id="runtime-new"),
        )
        connection = mock.Mock()
        connection.invoke_rpc.return_value = {"signed": "response"}
        self.state.instance_manifest = original
        self.state.instance_manifest_path = manifest_path
        self.state.instance_manifest_path_identity = server._path_identity(manifest_path)
        self.state.rpc_host = "127.0.0.1"
        self.state.rpc_port = 19876
        self.state.instance_id = "profile-a"
        self.state.auth_file = "C:/isolated-profile/auth.secret"

        with (
            mock.patch.object(
                server, "load_instance_manifest", return_value=refreshed
            ) as reload_manifest,
            mock.patch.object(server, "load_profile_secret", return_value=b"x" * 32),
            mock.patch.object(server, "make_mcp_runtime_identity", return_value=object()),
            mock.patch.object(
                server,
                "build_handshake_request_from_manifest",
                return_value={"client_nonce": "nonce"},
            ) as build_request,
            mock.patch.object(
                server,
                "verify_handshake_response_from_manifest",
                return_value=verified,
            ) as verify_response,
        ):
            server._authenticate_connection(connection, force=True)

        reload_manifest.assert_called_once_with(manifest_path)
        self.assertIs(build_request.call_args.kwargs["manifest"], refreshed)
        self.assertIs(verify_response.call_args.kwargs["manifest"], refreshed)
        refreshed.require_complete_runtime.assert_called_once_with()
        self.assertIs(self.state.instance_manifest, refreshed)
        self.assertEqual(self.state.rpc_session_id, "new-session-id")

    def test_session_refresh_rejects_immutable_manifest_change(self):
        baseline = SimpleNamespace(
            schema_version=1,
            profile_instance_id="profile-a",
            profile_path="C:/isolated-profile",
            auth_secret_file="C:/isolated-profile/auth.secret",
            rpc_host="127.0.0.1",
            rpc_port=19876,
            expected_profile_path_fingerprint="profile-fingerprint-a",
            created_at="2026-07-22T00:00:00Z",
        )
        changed = SimpleNamespace(
            **{
                **vars(baseline),
                "rpc_port": 29876,
                "require_complete_runtime": mock.Mock(),
            }
        )
        manifest_path = "C:/isolated-profile/instance-manifest.json"
        self.state.instance_manifest = baseline
        self.state.instance_manifest_path = manifest_path
        self.state.instance_manifest_path_identity = server._path_identity(manifest_path)
        self.state.rpc_host = "127.0.0.1"
        self.state.rpc_port = 19876
        self.state.instance_id = "profile-a"
        self.state.auth_file = "C:/isolated-profile/auth.secret"

        with (
            mock.patch.object(server, "load_instance_manifest", return_value=changed),
            mock.patch.object(server, "load_profile_secret") as load_secret,
            self.assertRaisesRegex(Exception, "immutable profile configuration"),
        ):
            server._authenticate_connection(mock.Mock(), force=True)

        load_secret.assert_not_called()
        self.assertIs(self.state.instance_manifest, baseline)

    def test_heartbeat_failure_logs_only_bounded_code_not_remote_secrets(self):
        manager = LeaseClientManager(session_token="rpc-session-secret")
        manager.store(
            LeaseCredential(
                lease_id="lease-a",
                document_session_uuid="doc-a",
                generation=1,
                token="lease-secret",
            )
        )
        connection = mock.Mock()
        connection.heartbeat_document_locks_batch.return_value = {
            "ok": False,
            "error": {
                "code": "DENIED",
                "message": "rpc-session-secret lease-secret",
            },
        }
        self.state.lease_manager = manager
        self.state.freecad_connection = connection

        with mock.patch.object(server.logger, "warning") as warning:
            successful = asyncio.run(server._lease_heartbeat_once())

        self.assertFalse(successful)
        self.assertNotIn("rpc-session-secret", repr(warning.call_args_list))
        self.assertNotIn("lease-secret", repr(warning.call_args_list))
        warning.assert_called_once_with(
            "Lease heartbeat batch failed (code=%s)", "DENIED"
        )
        payload, context = connection.heartbeat_document_locks_batch.call_args.args
        self.assertEqual(payload["leases"][0]["token"], "lease-secret")
        self.assertEqual(context.lease_credentials, ())

    def test_asset_creation_strategy_prompt_loads_resource(self):
        prompt = server.asset_creation_strategy()

        self.assertIn("Asset Creation Strategy for FreeCAD MCP", prompt)
        self.assertIn("get_objects()", prompt)
