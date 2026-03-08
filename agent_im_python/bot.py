"""Bot main class — event loop and message dispatch."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
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

    Enable debug logging to see trace IDs, API timing, WS traffic::

        bot = Bot(token="xxx", debug=True)
        # or at any time:
        Bot.enable_debug()
    """

    @staticmethod
    def enable_debug():
        """Enable verbose debug logging for the entire SDK.

        Configures the ``agent_im`` logger hierarchy so all SDK modules
        (api, ws, bot, context) emit DEBUG-level messages including:

        - API request/response with trace ID, status code, and timing
        - WebSocket message send/receive
        - Memory cache hit/miss
        - Context operations (reply, stream, handover)
        """
        sdk_logger = logging.getLogger("agent_im")
        sdk_logger.setLevel(logging.DEBUG)
        if not sdk_logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                "%(asctime)s [%(name)s] %(levelname)s %(message)s",
                datefmt="%H:%M:%S",
            ))
            sdk_logger.addHandler(handler)

    def __init__(
        self,
        token: str,
        base_url: str = "http://localhost:9800",
        transport: str = "websocket",
        debug: bool = False,
        key_file: str | None = ".agent_im_key",
        filter_by_subscription: bool = True,
    ):
        if debug:
            Bot.enable_debug()
        self.token = token
        self.base_url = base_url.rstrip("/")
        self._transport_type = transport
        self._filter_by_subscription = filter_by_subscription
        self._handler: Callable[[Context, Message], Coroutine] | None = None
        self._handover_handler: Callable[[Context, Message, dict], Coroutine] | None = None
        self._cancel_handler: Callable[[int, str], Coroutine] | None = None  # (conversation_id, stream_id)
        self._config_handler: Callable[[dict], Coroutine] | None = None
        self._bot_id: int = 0
        self._api = APIClient(self.base_url, self.token)
        self._key_file = key_file
        # Load persisted key if available
        if key_file:
            saved_token = self._load_key(key_file)
            if saved_token:
                self.token = saved_token
                self._api.update_token(saved_token)
                logger.info("bot: loaded saved key from %s", key_file)
        self._ws: WSTransport | None = None
        self._polling: PollingTransport | None = None
        self.subscription_config: dict[int, str] = {}  # conversation_id -> subscription_mode
        self._memory_cache: dict[int, dict[str, str]] = {}  # conv_id -> {key: content}
        self._prompt_cache: dict[int, str] = {}  # conv_id -> prompt

    def on_message(self, fn: Callable[[Context, Message], Coroutine]):
        """Decorator to register the message handler."""
        self._handler = fn
        return fn

    def on_task_cancel(self, fn: Callable[[int, str], Coroutine]):
        """Decorator to register the task cancellation handler."""
        self._cancel_handler = fn
        return fn

    def on_handover(self, fn: Callable[[Context, Message, dict], Coroutine]):
        """Decorator to register the task handover handler.

        Called when a message with content_type='task_handover' is received.
        The third argument is the parsed handover data from layers.data.
        """
        self._handover_handler = fn
        return fn

    def on_config(self, fn: Callable[[dict], Coroutine]):
        """Decorator to register the entity config handler (subscription modes)."""
        self._config_handler = fn
        return fn

    def run(self):
        """Synchronous entry point — runs the event loop."""
        asyncio.run(self.start())

    async def run_async(self):
        """Async entry point — alias for start()."""
        await self.start()

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
                on_key_upgrade=self._handle_key_upgrade,
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

    def _load_key(self, key_file: str) -> str | None:
        """Load a saved permanent key from file."""
        try:
            path = Path(key_file)
            if path.exists():
                key = path.read_text().strip()
                if key.startswith("aim_"):
                    return key
        except Exception:
            logger.debug("bot: could not load key from %s", key_file)
        return None

    def _save_key(self, key_file: str, token: str):
        """Save a permanent key to file."""
        try:
            Path(key_file).write_text(token)
            logger.info("bot: saved permanent key to %s", key_file)
        except Exception:
            logger.exception("bot: failed to save key to %s", key_file)

    async def _handle_key_upgrade(self, new_token: str):
        """Handle a key upgrade from bootstrap to permanent."""
        self.token = new_token
        self._api.update_token(new_token)
        if self._key_file:
            self._save_key(self._key_file, new_token)
        logger.info("bot: key upgraded to permanent key")

    # --- Internal dispatch ---

    async def _dispatch_message(self, data: dict):
        """Handle an incoming message.new event."""
        msg = _dict_to_message(data)

        # Skip own messages
        if msg.sender_type == "bot" and msg.sender_id == self._bot_id:
            logger.debug("bot: skipping own message id=%d", msg.id)
            return

        # Auto-filter by subscription mode
        if self._filter_by_subscription:
            mode = self.subscription_config.get(msg.conversation_id, "subscribe_all")
            if mode == "mention_only" and not msg.is_mentioned(self._bot_id):
                logger.debug("bot: skipping msg id=%d (mention_only, not mentioned)", msg.id)
                return

        logger.debug(
            "bot: incoming msg id=%d conv=%d type=%s from=%s:%d summary=%.60s",
            msg.id, msg.conversation_id, msg.content_type or "text",
            msg.sender_type, msg.sender_id,
            (msg.layers.summary or "")[:60],
        )

        # Auto-load conversation memories + prompt
        memories, prompt = await self._get_conversation_context(msg.conversation_id)

        ctx = Context(
            conversation_id=msg.conversation_id,
            api=self._api,
            send_ws_fn=self._ws.send_message if self._ws else None,
            memories=memories,
            prompt=prompt,
        )

        # Dispatch task_handover to dedicated handler if registered
        if msg.content_type == "task_handover" and self._handover_handler is not None:
            handover_data = {}
            if isinstance(msg.layers.data, dict):
                handover_data = msg.layers.data
            try:
                await self._handover_handler(ctx, msg, handover_data)
            except Exception:
                logger.exception("bot: error in handover handler")
            return

        if self._handler is None:
            return

        try:
            await self._handler(ctx, msg)
        except Exception:
            logger.exception("bot: error in message handler")

    async def _dispatch_stream(self, stream_type: str, data: dict):
        """Handle stream events."""
        logger.debug("bot: stream event %s", stream_type)

        # Handle memory updates — invalidate cache
        if stream_type == "conversation.memory_updated":
            conv_id = data.get("conversation_id", 0)
            if conv_id and conv_id in self._memory_cache:
                del self._memory_cache[conv_id]
                self._prompt_cache.pop(conv_id, None)
                logger.debug("bot: invalidated memory cache for conv %d", conv_id)
            return

        # Handle task cancellation
        if stream_type == "task.cancel" and self._cancel_handler:
            conversation_id = data.get("conversation_id", 0)
            stream_id = data.get("stream_id", "")
            if conversation_id and stream_id:
                try:
                    await self._cancel_handler(conversation_id, stream_id)
                except Exception:
                    logger.exception("bot: error in task cancel handler")

    async def _get_conversation_context(self, conv_id: int) -> tuple[dict[str, str], str]:
        """Load memories and prompt for a conversation, using cache."""
        if conv_id in self._memory_cache:
            logger.debug("bot: context cache hit for conv %d", conv_id)
            return self._memory_cache[conv_id], self._prompt_cache.get(conv_id, "")

        logger.debug("bot: context cache miss for conv %d, fetching...", conv_id)
        try:
            result = await self._api.get_conversation_context(conv_id)
            memories = {}
            for m in result.get("memories", []):
                key = m.get("key", "")
                content = m.get("content", "")
                if key:
                    memories[key] = content
            prompt = result.get("prompt", "")
            self._memory_cache[conv_id] = memories
            self._prompt_cache[conv_id] = prompt
            logger.debug(
                "bot: loaded context for conv %d: %d memories, prompt=%d chars",
                conv_id, len(memories), len(prompt),
            )
            return memories, prompt
        except Exception:
            logger.debug("bot: failed to load context for conv %d", conv_id)
            return {}, ""

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
