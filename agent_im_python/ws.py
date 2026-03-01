"""WebSocket transport layer with auto-reconnect."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Coroutine

import websockets
import websockets.asyncio.client

from .models import MessageLayers, _layers_to_dict

logger = logging.getLogger("agent_im.ws")


class WSTransport:
    """WebSocket client that handles connection, reconnect, and message dispatch."""

    def __init__(self, base_url: str, token: str):
        # Convert http(s):// to ws(s)://
        ws_url = base_url.replace("https://", "wss://").replace("http://", "ws://")
        self._url = f"{ws_url.rstrip('/')}/api/v1/ws?token={token}"
        self._ws: websockets.asyncio.client.ClientConnection | None = None
        self._running = False

    async def receive_loop(
        self,
        on_message: Callable[[dict], Coroutine],
        on_stream: Callable[[str, dict], Coroutine] | None = None,
    ):
        """Main loop: connect, receive, dispatch, auto-reconnect with exponential backoff."""
        self._running = True
        backoff = 1.0

        while self._running:
            try:
                async with websockets.asyncio.client.connect(
                    self._url,
                    ping_interval=25,
                    ping_timeout=60,
                    max_size=64 * 1024,
                ) as ws:
                    self._ws = ws
                    backoff = 1.0  # reset on successful connect
                    logger.info("ws: connected")

                    async for raw in ws:
                        try:
                            envelope = json.loads(raw)
                        except json.JSONDecodeError:
                            continue

                        msg_type = envelope.get("type", "")
                        data = envelope.get("data", {})

                        if msg_type == "message.new":
                            await on_message(data)
                        elif msg_type.startswith("stream.") and on_stream:
                            await on_stream(msg_type, data)
                        elif msg_type == "pong":
                            pass  # keepalive response
                        elif msg_type == "task.cancel":
                            # Dispatch to cancellation handler
                            if on_stream:
                                await on_stream("task.cancel", data)
                        elif msg_type == "task.cancelled":
                            if on_stream:
                                await on_stream("task.cancelled", data)
                        elif msg_type == "error":
                            logger.warning("ws: server error: %s", data)

            except websockets.exceptions.ConnectionClosed as e:
                logger.warning("ws: connection closed: %s", e)
            except (OSError, websockets.exceptions.WebSocketException) as e:
                logger.warning("ws: connection error: %s", e)
            finally:
                self._ws = None

            if not self._running:
                break

            logger.info("ws: reconnecting in %.0fs...", backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)

    async def send(self, msg_type: str, data: dict[str, Any]):
        """Send a typed message through the WebSocket."""
        if self._ws is None:
            raise RuntimeError("WebSocket not connected")
        envelope = json.dumps({"type": msg_type, "data": data})
        await self._ws.send(envelope)

    async def send_message(
        self,
        conversation_id: int,
        layers: MessageLayers,
        stream_id: str = "",
        stream_type: str = "",
    ):
        """Send a message.send envelope."""
        data: dict[str, Any] = {
            "conversation_id": conversation_id,
            "layers": _layers_to_dict(layers),
        }
        if stream_id:
            data["stream_id"] = stream_id
        if stream_type:
            data["stream_type"] = stream_type
        await self.send("message.send", data)

    async def send_task_cancel(self, conversation_id: int, stream_id: str):
        """Send a task.cancel request to stop a running task."""
        data: dict[str, Any] = {
            "conversation_id": conversation_id,
            "stream_id": stream_id,
        }
        await self.send("task.cancel", data)

    def stop(self):
        self._running = False
        if self._ws:
            asyncio.get_event_loop().call_soon_threadsafe(
                asyncio.ensure_future, self._ws.close()
            )
