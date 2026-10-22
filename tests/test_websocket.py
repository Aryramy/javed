"""Tests for WebSocket transport and event routing."""

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from javed.main import app


def test_websocket_connection_handshake() -> None:
    """Test WebSocket connection establishment and initial welcome handshake."""
    with TestClient(app) as client:
        with client.websocket_connect("/api/v1/ws") as websocket:
            data = websocket.receive_json()
            assert data["type"] == "connection_established"
            assert "client_id" in data["payload"]
            assert "server_time" in data["payload"]


def test_websocket_ping_pong() -> None:
    """Test client ping receives server pong with correlated ID and timestamp."""
    with TestClient(app) as client:
        with client.websocket_connect("/api/v1/ws") as websocket:
            # Consume welcome handshake
            websocket.receive_json()

            # Send ping
            ping_msg = {
                "type": "ping",
                "correlation_id": "req-12345",
                "payload": {"client_time": 1729590000.0},
            }
            websocket.send_json(ping_msg)

            # Receive pong
            response = websocket.receive_json()
            assert response["type"] == "pong"
            assert response["correlation_id"] == "req-12345"
            assert response["payload"]["client_time"] == 1729590000.0
            assert "server_time" in response["payload"]


def test_websocket_heartbeat() -> None:
    """Test client heartbeat receives heartbeat_ack."""
    with TestClient(app) as client:
        with client.websocket_connect("/api/v1/ws") as websocket:
            websocket.receive_json()

            heartbeat_msg = {
                "type": "heartbeat",
                "correlation_id": "hb-001",
                "payload": {"client_time": 1729590010.0},
            }
            websocket.send_json(heartbeat_msg)

            response = websocket.receive_json()
            assert response["type"] == "heartbeat_ack"
            assert response["correlation_id"] == "hb-001"
            assert "server_time" in response["payload"]


def test_websocket_status_request() -> None:
    """Test client status_request returns status_response."""
    with TestClient(app) as client:
        with client.websocket_connect("/api/v1/ws") as websocket:
            websocket.receive_json()

            websocket.send_json({"type": "status_request", "correlation_id": "stat-001"})
            response = websocket.receive_json()
            assert response["type"] == "status_response"
            assert response["correlation_id"] == "stat-001"
            assert "backend_version" in response["payload"]
            assert "active_connections" in response["payload"]


def test_websocket_echo() -> None:
    """Test client echo payload is returned unchanged."""
    with TestClient(app) as client:
        with client.websocket_connect("/api/v1/ws") as websocket:
            websocket.receive_json()

            websocket.send_json({"type": "echo", "payload": {"foo": "bar", "count": 42}})
            response = websocket.receive_json()
            assert response["type"] == "echo_response"
            assert response["payload"]["foo"] == "bar"
            assert response["payload"]["count"] == 42


def test_websocket_malformed_json_handling() -> None:
    """Test sending malformed JSON does not crash connection and returns error envelope."""
    with TestClient(app) as client:
        with client.websocket_connect("/api/v1/ws") as websocket:
            websocket.receive_json()

            websocket.send_text("this is not valid json")
            response = websocket.receive_json()
            assert response["type"] == "error"
            assert response["payload"]["code"] == "INVALID_JSON"


def test_websocket_origin_enforcement() -> None:
    """Test connecting from an unauthorized origin is rejected with code 1008."""
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(
                "/api/v1/ws",
                headers={"origin": "http://malicious-website.com"},
            ):
                pass
        assert exc_info.value.code == 1008
