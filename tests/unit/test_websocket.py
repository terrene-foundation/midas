"""Tests for WebSocket endpoint — T-23-02.

Covers: connection, subscribe/unsubscribe, ping/pong, invalid JSON, channel validation.
Uses mock WebSocket (Tier 1 unit tests).
"""

import json

import pytest
from fastapi import WebSocketDisconnect

from midas.api.websocket import ConnectionManager, VALID_CHANNELS


class MockWebSocket:
    def __init__(self):
        self.sent: list[dict] = []
        self._incoming: list[str] = []
        self._accepted = False

    def add_incoming(self, data: str):
        self._incoming.append(data)

    async def accept(self):
        self._accepted = True

    async def send_json(self, data: dict):
        self.sent.append(data)

    async def receive_text(self) -> str:
        if self._incoming:
            return self._incoming.pop(0)
        raise WebSocketDisconnect()


async def _failing_send(data):
    raise Exception("connection dead")


class TestConnectionManager:
    def test_init_has_all_channels(self):
        mgr = ConnectionManager()
        for ch in VALID_CHANNELS:
            assert ch in mgr._connections
            assert mgr._connections[ch] == []

    @pytest.mark.asyncio
    async def test_connect_adds_to_channels(self):
        mgr = ConnectionManager()
        ws = MockWebSocket()
        await mgr.connect(ws, ["regime", "decisions"])
        assert ws in mgr._connections["regime"]
        assert ws in mgr._connections["decisions"]
        assert ws not in mgr._connections["portfolio"]

    @pytest.mark.asyncio
    async def test_disconnect_removes_from_all(self):
        mgr = ConnectionManager()
        ws = MockWebSocket()
        await mgr.connect(ws, ["regime", "decisions"])
        mgr.disconnect(ws)
        assert ws not in mgr._connections["regime"]
        assert ws not in mgr._connections["decisions"]

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_channel(self):
        mgr = ConnectionManager()
        ws1 = MockWebSocket()
        ws2 = MockWebSocket()
        await mgr.connect(ws1, ["regime"])
        await mgr.connect(ws2, ["decisions"])
        await mgr.broadcast("regime", {"type": "regime_change", "band": "elevated"})
        assert len(ws1.sent) == 1
        assert ws1.sent[0]["type"] == "regime_change"
        assert len(ws2.sent) == 0

    @pytest.mark.asyncio
    async def test_broadcast_removes_dead_connections(self):
        mgr = ConnectionManager()
        ws = MockWebSocket()
        await mgr.connect(ws, ["regime"])
        ws.send_json = _failing_send
        await mgr.broadcast("regime", {"type": "test"})
        assert ws not in mgr._connections["regime"]


class TestWebSocketEndpoint:
    @pytest.mark.asyncio
    async def test_full_flow(self):
        from midas.api.websocket import WebSocketRouter

        router = WebSocketRouter()
        ws = MockWebSocket()
        ws.add_incoming(json.dumps({"channels": ["regime", "portfolio"]}))
        ws.add_incoming(json.dumps({"type": "ping"}))
        ws.add_incoming(json.dumps({"type": "subscribe", "channels": ["debate"]}))
        ws.add_incoming(json.dumps({"type": "unsubscribe", "channels": ["portfolio"]}))

        await router.websocket_endpoint(ws)

        assert ws._accepted
        connected_msg = ws.sent[0]
        assert connected_msg["type"] == "connected"
        assert "regime" in connected_msg["channels"]

        pong_msg = ws.sent[1]
        assert pong_msg["type"] == "pong"

        sub_msg = ws.sent[2]
        assert sub_msg["type"] == "subscribed"
        assert "debate" in sub_msg["channels"]

        unsub_msg = ws.sent[3]
        assert unsub_msg["type"] == "unsubscribed"
        assert "portfolio" not in unsub_msg["channels"]

    @pytest.mark.asyncio
    async def test_invalid_json(self):
        from midas.api.websocket import WebSocketRouter

        router = WebSocketRouter()
        ws = MockWebSocket()
        ws.add_incoming(json.dumps({"channels": ["regime"]}))
        ws.add_incoming("not valid json{{{")

        await router.websocket_endpoint(ws)

        error_msg = [m for m in ws.sent if m.get("type") == "error"]
        assert len(error_msg) == 1
        assert "Invalid JSON" in error_msg[0]["detail"]

    @pytest.mark.asyncio
    async def test_unknown_message_type(self):
        from midas.api.websocket import WebSocketRouter

        router = WebSocketRouter()
        ws = MockWebSocket()
        ws.add_incoming(json.dumps({"channels": ["regime"]}))
        ws.add_incoming(json.dumps({"type": "unknown_thing"}))

        await router.websocket_endpoint(ws)

        error_msg = [m for m in ws.sent if m.get("type") == "error"]
        assert any("Unknown type" in m["detail"] for m in error_msg)

    @pytest.mark.asyncio
    async def test_invalid_channel_ignored(self):
        from midas.api.websocket import WebSocketRouter

        router = WebSocketRouter()
        ws = MockWebSocket()
        ws.add_incoming(json.dumps({"channels": ["regime", "hacked_channel"]}))

        await router.websocket_endpoint(ws)

        connected_msg = ws.sent[0]
        assert "hacked_channel" not in connected_msg["channels"]
        assert "regime" in connected_msg["channels"]
