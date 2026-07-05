import asyncio
import unittest
from unittest import mock

from freecad_mcp import server


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

        with mock.patch.object(server, "FreeCADConnection", return_value=connection) as factory:
            result = server.get_freecad_connection()

        self.assertIs(result, connection)
        factory.assert_called_once_with(host="localhost", port=9875)
        connection.ping.assert_called_once_with()

    def test_shutdown_disconnects_existing_connection(self):
        connection = mock.Mock()
        self.state.freecad_connection = connection

        async def run_lifespan():
            async with server.server_lifespan(object()):
                self.assertIs(server.state.freecad_connection, connection)

        asyncio.run(run_lifespan())

        connection.disconnect.assert_called_once_with()
        self.assertIsNone(server.state.freecad_connection)

    def test_asset_creation_strategy_prompt_loads_resource(self):
        prompt = server.asset_creation_strategy()

        self.assertIn("Asset Creation Strategy for FreeCAD MCP", prompt)
        self.assertIn("get_objects()", prompt)
