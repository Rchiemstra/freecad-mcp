from unittest.mock import MagicMock

from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp import server as server_module


def test_client_forwards_sync_nonce():
    connection = FreeCADConnection.__new__(FreeCADConnection)
    connection.server = MagicMock()
    connection.server.check_rpc_sync.return_value = {
        "success": True,
        "nonce": "probe-123",
    }

    assert connection.check_rpc_sync("probe-123") == {
        "success": True,
        "nonce": "probe-123",
    }
    connection.server.check_rpc_sync.assert_called_once_with("probe-123")


def test_mcp_sync_check_rejects_nonce_mismatch(monkeypatch):
    connection = MagicMock()
    connection.check_rpc_sync.return_value = {
        "success": True,
        "nonce": "stale-response-nonce",
    }
    monkeypatch.setattr(server_module, "get_freecad_connection", lambda: connection)
    monkeypatch.setattr(server_module.uuid, "uuid4", lambda: MagicMock(hex="current-nonce"))

    response = server_module.check_rpc_sync(None)

    assert response.isError is True
    assert response.structuredContent["synchronized"] is False
    assert response.structuredContent["expected_nonce"] == "current-nonce"


def test_mcp_sync_check_accepts_matching_nonce(monkeypatch):
    connection = MagicMock()
    connection.check_rpc_sync.return_value = {
        "success": True,
        "nonce": "current-nonce",
    }
    monkeypatch.setattr(server_module, "get_freecad_connection", lambda: connection)
    monkeypatch.setattr(server_module.uuid, "uuid4", lambda: MagicMock(hex="current-nonce"))

    response = server_module.check_rpc_sync(None)

    assert response.isError is False
    assert "synchronized" in response.content[0].text
