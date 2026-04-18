"""WebSocket endpoint for real-time updates.

Implements: T-23-02 — channel subscription with regime, decision, and portfolio events.

Ref: specs/09 S5, specs/10 S3
"""

import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from midas.api.auth import decode_access_token, jwt_auth_enabled

logger = logging.getLogger(__name__)

VALID_CHANNELS = {"regime", "decisions", "portfolio", "debate", "pulse", "notifications"}


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {ch: [] for ch in VALID_CHANNELS}

    async def connect(self, ws: WebSocket, channels: list[str]) -> None:
        await ws.accept()
        for ch in channels:
            if ch in self._connections:
                self._connections[ch].append(ws)
        logger.info("ws.connect", extra={"channels": channels})

    def disconnect(self, ws: WebSocket) -> None:
        for conns in self._connections.values():
            if ws in conns:
                conns.remove(ws)

    async def broadcast(self, channel: str, data: dict[str, Any]) -> None:
        conns = self._connections.get(channel, [])
        dead = []
        for ws in conns:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            conns.remove(ws)


manager = ConnectionManager()


class WebSocketRouter:
    def __init__(self) -> None:
        self.router = APIRouter()
        self.router.add_api_websocket_route("/ws", self.websocket_endpoint)

    async def _authenticate(self, ws: WebSocket) -> dict[str, Any] | None:
        """Check JWT auth. In dev mode (no JWT_SECRET), allow all."""
        if not jwt_auth_enabled():
            return {"sub": "dev", "email": ""}
        # Expect token as query param: ws://host/api/v1/ws?token=xxx
        token = ws.query_params.get("token", "")
        if not token:
            return None
        try:
            return decode_access_token(token)
        except Exception:
            return None

    async def websocket_endpoint(self, ws: WebSocket) -> None:
        channels: list[str] = []
        try:
            user = await self._authenticate(ws)
            if user is None and jwt_auth_enabled():
                await ws.close(code=4001, reason="Authentication required")
                return

            await ws.accept()
            logger.info("ws.connected", extra={"user_id": user.get("sub", "") if user else ""})

            init_msg = await ws.receive_text()
            try:
                init_data = json.loads(init_msg)
                requested = init_data.get("channels", ["regime", "decisions"])
                channels = [ch for ch in requested if ch in VALID_CHANNELS]
            except (ValueError, TypeError):
                channels = ["regime", "decisions"]

            for ch in channels:
                manager._connections[ch].append(ws)

            await ws.send_json({"type": "connected", "channels": channels})

            while True:
                raw = await ws.receive_text()
                try:
                    msg = json.loads(raw)
                except (ValueError, TypeError):
                    await ws.send_json({"type": "error", "detail": "Invalid JSON"})
                    continue

                msg_type = msg.get("type", "")
                if msg_type == "subscribe":
                    new_chs = [ch for ch in msg.get("channels", []) if ch in VALID_CHANNELS]
                    for ch in new_chs:
                        if ch not in channels:
                            channels.append(ch)
                            manager._connections[ch].append(ws)
                    await ws.send_json({"type": "subscribed", "channels": channels})
                elif msg_type == "unsubscribe":
                    drop_chs = msg.get("channels", [])
                    for ch in drop_chs:
                        if ch in channels and ch in manager._connections:
                            channels.remove(ch)
                            if ws in manager._connections[ch]:
                                manager._connections[ch].remove(ws)
                    await ws.send_json({"type": "unsubscribed", "channels": channels})
                elif msg_type == "ping":
                    await ws.send_json({"type": "pong"})
                else:
                    await ws.send_json({"type": "error", "detail": f"Unknown type: {msg_type}"})

        except WebSocketDisconnect:
            pass
        finally:
            manager.disconnect(ws)
            logger.info("ws.disconnected", extra={"channels": channels})
