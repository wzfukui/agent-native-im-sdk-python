"""Bot main class — event loop and message dispatch."""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Coroutine

from .api import APIClient
from .context import Context
from .models import Message, _dict_to_message
from .ws import WSTransport
from .polling import PollingTransport

logger = logging.getLogger("agent_im")


class Bot:
    """Main entry point for building an Agent-Native IM bot.

    Usage::

        bot = Bot(token="xxx", base_url="http://localhost:9800")

        @bot.on_message
        async def handle(ctx, msg):
            await ctx.reply(summary="Hello!")

        bot.run()
    """

    def __init__(
        self,
        token: str,
        base_url: str = "http://localhost:9800",
        transport: str = "websocket",
    ):
        self.token = token
        self.base_url = base_url.rstrip("/")
        self._transport_type = transport
        self._handler: Callable[[Context, Message], Coroutine] | None = None
        self._cancel_handler: Callable[[int, str], Coroutine] | None = None  # (conversation_id, stream_id)
        self._config_handler: Callable[[dict], Coroutine] | None = None
        self._bot_id: int = 0
        self._api = APIClient(self.base_url, self.token)
        self._ws: WSTransport | None = None
        self._polling: PollingTransport | None = None
        self.subscription_config: dict[int, str] = {}  # conversation_id -> subscription_mode

    def on_message(self, fn: Callable[[Context, Message], Coroutine]):
        """Decorator to register the message handler."""
        self._handler = fn
        return fn

    def on_task_cancel(self, fn: Callable[[int, str], Coroutine]):
        """Decorator to register the task cancellation handler."""
        self._cancel_handler = fn
        return fn

    def on_config(self, fn: Callable[[dict], Coroutine]):
        """Decorator to register the entity config handler (subscription modes)."""
        self._config_handler = fn
        return fn

    def run(self):
        """Synchronous entry point — runs the event loop."""
        asyncio.run(self.start())

    async def start(self):
        """Async entry point — connect and start receiving."""
        # Verify connectivity
        me = await self._api.get_me()
        self._bot_id = me.id
        logger.info("bot: connected as %s (id=%d)", me.name, me.id)

        if self._transport_type == "websocket":
            self._ws = WSTransport(self.base_url, self.token)
            await self._ws.receive_loop(
                on_message=self._dispatch_message,
                on_stream=self._dispatch_stream,
                on_config=self._dispatch_config,
            )
        else:
            self._polling = PollingTransport(self._api)
            await self._polling.receive_loop(
                on_message=self._dispatch_message,
            )

    async def stop(self):
        """Stop the bot gracefully."""
        if self._ws:
            self._ws.stop()
        if self._polling:
            self._polling.stop()
        await self._api.close()

    # --- Internal dispatch ---

    async def _dispatch_message(self, data: dict):
        """Handle an incoming message.new event."""
        msg = _dict_to_message(data)

        # Skip own messages
        if msg.sender_type == "bot" and msg.sender_id == self._bot_id:
            return

        if self._handler is None:
            return

        ctx = Context(
            conversation_id=msg.conversation_id,
            api=self._api,
            send_ws_fn=self._ws.send_message if self._ws else None,
        )

        try:
            await self._handler(ctx, msg)
        except Exception:
            logger.exception("bot: error in message handler")

    async def _dispatch_stream(self, stream_type: str, data: dict):
        """Handle stream events."""
        logger.debug("bot: stream event %s", stream_type)

        # Handle task cancellation
        if stream_type == "task.cancel" and self._cancel_handler:
            conversation_id = data.get("conversation_id", 0)
            stream_id = data.get("stream_id", "")
            if conversation_id and stream_id:
                try:
                    await self._cancel_handler(conversation_id, stream_id)
                except Exception:
                    logger.exception("bot: error in task cancel handler")

    async def _dispatch_config(self, data: dict):
        """Handle entity.config event — store subscription modes."""
        conversations = data.get("conversations", [])
        for conv in conversations:
            conv_id = conv.get("conversation_id", 0)
            mode = conv.get("subscription_mode", "mention_only")
            if conv_id:
                self.subscription_config[conv_id] = mode
        logger.info("bot: subscription config received for %d conversations", len(conversations))

        if self._config_handler:
            try:
                await self._config_handler(data)
            except Exception:
                logger.exception("bot: error in config handler")
