"""Long polling transport layer."""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Coroutine

from .api import APIClient

logger = logging.getLogger("agent_im.polling")


class PollingTransport:
    """Fetches updates via GET /updates long polling.

    Note: cannot receive stream.start/delta events (server design limitation).
    Only persisted messages are returned.
    """

    def __init__(self, api: APIClient, poll_timeout: int = 30):
        self._api = api
        self._poll_timeout = poll_timeout
        self._running = False

    async def receive_loop(
        self,
        on_message: Callable[[dict], Coroutine],
        on_stream: Callable[[str, dict], Coroutine] | None = None,
    ):
        """Poll for updates in a loop. on_stream is accepted for interface compat but unused."""
        self._running = True
        offset = 0

        while self._running:
            try:
                messages = await self._api.get_updates(
                    offset=offset, timeout=self._poll_timeout
                )
                for msg in messages:
                    if msg.id > offset:
                        offset = msg.id
                    # Convert back to dict for uniform dispatch
                    await on_message({
                        "id": msg.id,
                        "conversation_id": msg.conversation_id,
                        "stream_id": msg.stream_id,
                        "content_type": msg.content_type,
                        "sender_type": msg.sender_type,
                        "sender_id": msg.sender_id,
                        "attachments": msg.attachments,
                        "mentions": msg.mentions,
                        "mentioned_entity_ids": msg.mentioned_entity_ids,
                        "reply_to": msg.reply_to,
                        "reactions": msg.reactions,
                        "edited_at": msg.edited_at,
                        "layers": {
                            "thinking": msg.layers.thinking,
                            "summary": msg.layers.summary,
                            "data": msg.layers.data,
                        },
                        "created_at": msg.created_at,
                    })
            except Exception as e:
                logger.warning("polling: error: %s", e)
                if self._running:
                    await asyncio.sleep(3)

    def stop(self):
        self._running = False
