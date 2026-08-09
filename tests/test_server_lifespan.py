import asyncio
import threading
import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest import mock

from freecad_mcp import server
from freecad_mcp.server_ops import manifest_auth
from freecad_mcp.server_ops.heartbeat import lease_heartbeat_once


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
        connection._identity_lock = threading.RLock()
        self.state.freecad_connection = connection
        self.state.rpc_session.mark_connected("rpc-session")
        self.state.rpc_session_id = "session-id"
        self.state.rpc_session_expires_at = "2099-01-01T00:00:00Z"
        self.state.authenticated_manifest = object()

        async def run_lifespan():
            async with server.server_lifespan(object()):
                self.assertIs(server.state.freecad_connection, connection)

        asyncio.run(run_lifespan())

        connection.disconnect.assert_called_once_with()
        self.assertIsNone(server.state.freecad_connection)
        self.assertFalse(server.state.rpc_session.connected)
        self.assertIsNone(server.state.rpc_session_id)
        self.assertIsNone(server.state.rpc_session_expires_at)
        self.assertIsNone(server.state.authenticated_manifest)

    def test_connection_initialization_failure_closes_transport_and_fences_session(
        self,
    ):
        connection = mock.Mock()
        connection._identity_lock = threading.RLock()
        connection.ping.return_value = False
        self.state.rpc_session.mark_connected("old-session")

        with (
            mock.patch.object(server, "FreeCADConnection", return_value=connection),
            self.assertRaisesRegex(Exception, "Failed to connect"),
        ):
            server.get_freecad_connection()

        connection.disconnect.assert_called_once_with()
        self.assertIsNone(server.state.freecad_connection)
        self.assertFalse(server.state.rpc_session.connected)

    def test_shutdown_clears_sensitive_state_even_when_transport_close_fails(self):
        connection = mock.Mock()
        connection.disconnect.side_effect = RuntimeError("remote echoed auth-secret")
        self.state.freecad_connection = connection
        self.state.rpc_session.mark_connected("auth-secret")

        async def run_lifespan():
            with mock.patch.object(server.logger, "warning") as warning:
                async with server.server_lifespan(object()):
                    pass
                self.assertNotIn("auth-secret", repr(warning.call_args_list))

        asyncio.run(run_lifespan())

        self.assertIsNone(self.state.freecad_connection)
        self.assertFalse(self.state.rpc_session.connected)

    def test_session_refresh_margin_is_fail_closed(self):
        now = datetime.now(UTC)
        self.state.rpc_session_expires_at = (now + timedelta(minutes=10)).isoformat()
        self.assertFalse(server._session_needs_refresh())

        self.state.rpc_session_expires_at = (now + timedelta(seconds=30)).isoformat()
        self.assertTrue(server._session_needs_refresh())

        self.state.rpc_session_expires_at = "not-a-timestamp"
        self.assertTrue(server._session_needs_refresh())

    def test_authenticated_session_refresh_replaces_authentication_only(self):
        expiry = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
        manifest = SimpleNamespace(auth_secret_file="profile.auth")
        verified = SimpleNamespace(
            session_token="new-session",
            session_id="new-session-id",
            session_expires_at=expiry,
            manifest=SimpleNamespace(addon_runtime_id="addon-runtime"),
        )
        connection = mock.Mock()
        connection._identity_lock = threading.RLock()
        connection.invoke_rpc.return_value = {"signed": "response"}
        self.state.instance_manifest = manifest
        self.state.rpc_session.mark_connected("old-session")

        with (
            mock.patch.object(
                manifest_auth, "load_profile_secret", return_value=b"x" * 32
            ),
            mock.patch.object(
                manifest_auth, "make_mcp_runtime_identity", return_value=object()
            ),
            mock.patch.object(
                manifest_auth,
                "build_handshake_request_from_manifest",
                return_value={"client_nonce": "nonce"},
            ),
            mock.patch.object(
                manifest_auth,
                "verify_handshake_response_from_manifest",
                return_value=verified,
            ),
        ):
            server._authenticate_connection(connection, force=True)

        self.assertTrue(self.state.rpc_session.connected)
        self.assertEqual(self.state.rpc_session_id, "new-session-id")
        self.assertEqual(self.state.rpc_session_expires_at, expiry)
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
        expiry = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
        verified = SimpleNamespace(
            session_token="new-session-token",
            session_id="new-session-id",
            session_expires_at=expiry,
            manifest=SimpleNamespace(addon_runtime_id="runtime-new"),
        )
        connection = mock.Mock()
        connection._identity_lock = threading.RLock()
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
                manifest_auth, "load_instance_manifest", return_value=refreshed
            ) as reload_manifest,
            mock.patch.object(
                manifest_auth, "load_profile_secret", return_value=b"x" * 32
            ),
            mock.patch.object(
                manifest_auth, "make_mcp_runtime_identity", return_value=object()
            ),
            mock.patch.object(
                manifest_auth,
                "build_handshake_request_from_manifest",
                return_value={"client_nonce": "nonce"},
            ) as build_request,
            mock.patch.object(
                manifest_auth,
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
            mock.patch.object(
                manifest_auth, "load_instance_manifest", return_value=changed
            ),
            mock.patch.object(manifest_auth, "load_profile_secret") as load_secret,
            self.assertRaisesRegex(Exception, "immutable profile configuration"),
        ):
            server._authenticate_connection(mock.Mock(), force=True)

        load_secret.assert_not_called()
        self.assertIs(self.state.instance_manifest, baseline)

    def test_removed_heartbeat_is_inert(self):
        self.assertFalse(asyncio.run(lease_heartbeat_once()))

    def test_asset_creation_strategy_prompt_loads_resource(self):
        prompt = server.asset_creation_strategy()

        self.assertIn("Asset Creation Strategy for FreeCAD MCP", prompt)
        self.assertIn("get_objects()", prompt)
