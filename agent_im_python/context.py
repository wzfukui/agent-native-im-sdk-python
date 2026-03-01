"""Message context — reply and streaming helpers."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any

from .api import APIClient
from .models import MessageLayers, StatusLayer, _layers_to_dict


class Context:
    """Created for each incoming message, provides reply/stream helpers."""

    def __init__(
        self,
        conversation_id: int,
        api: APIClient,
        send_ws_fn=None,
    ):
        self.conversation_id = conversation_id
        self._api = api
        self._send_ws = send_ws_fn

    # --- Simple reply ---

    async def reply(
        self,
        summary: str = "",
        thinking: str = "",
        data: Any = None,
        interaction=None,
    ) -> None:
        """Send a persisted reply message."""
        layers = MessageLayers(
            summary=summary,
            thinking=thinking,
            data=data,
            interaction=interaction,
        )
        await self._api.send_message(self.conversation_id, layers)

    # --- Conversation ---

    async def update_title(self, title: str) -> None:
        """Update the conversation title."""
        await self._api.update_conversation(self.conversation_id, title)

    # --- Streaming primitives ---

    async def stream_start(
        self,
        phase: str = "processing",
        text: str = "",
        progress: float = 0.0,
    ) -> str:
        """Start a new stream. Returns stream_id."""
        stream_id = uuid.uuid4().hex[:12]
        layers = MessageLayers(
            status=StatusLayer(phase=phase, progress=progress, text=text),
        )
        if self._send_ws:
            await self._send_ws(
                self.conversation_id, layers,
                stream_id=stream_id, stream_type="start",
            )
        return stream_id

    async def stream_delta(
        self,
        stream_id: str,
        summary: str = "",
        progress: float = 0.0,
        text: str = "",
        phase: str = "processing",
    ) -> None:
        """Send an ephemeral stream update."""
        layers = MessageLayers(
            summary=summary,
            status=StatusLayer(phase=phase, progress=progress, text=text),
        )
        if self._send_ws:
            await self._send_ws(
                self.conversation_id, layers,
                stream_id=stream_id, stream_type="delta",
            )

    async def stream_end(
        self,
        stream_id: str,
        summary: str = "",
        data: Any = None,
    ) -> None:
        """End a stream (persisted message)."""
        layers = MessageLayers(summary=summary, data=data)
        if self._send_ws:
            await self._send_ws(
                self.conversation_id, layers,
                stream_id=stream_id, stream_type="end",
            )
        else:
            await self._api.send_message(
                self.conversation_id, layers, stream_id=stream_id,
            )

    # --- Convenience helpers ---

    async def stream_status(
        self,
        text: str,
        progress: float = 0.0,
        phase: str = "processing",
    ) -> str:
        """Convenience: auto-create stream + send delta. Returns stream_id."""
        stream_id = await self.stream_start(phase=phase, text=text, progress=progress)
        return stream_id

    @asynccontextmanager
    async def stream(self, phase: str = "processing"):
        """Async context manager for stream lifecycle.

        Usage::

            async with ctx.stream() as s:
                await s.update("Step 1...", progress=0.3)
                await s.update("Step 2...", progress=0.7)
                s.result = "Final answer"
        """
        sc = StreamContext(self, phase)
        await sc._start()
        try:
            yield sc
        finally:
            await sc._end()


class StreamContext:
    """Managed stream lifecycle within an async context manager."""

    def __init__(self, ctx: Context, phase: str):
        self._ctx = ctx
        self._phase = phase
        self._stream_id = ""
        self.result: str = ""
        self.result_data: Any = None

    async def _start(self):
        self._stream_id = await self._ctx.stream_start(phase=self._phase)

    async def update(
        self,
        text: str = "",
        progress: float = 0.0,
        summary: str = "",
    ) -> None:
        """Send a stream delta update."""
        await self._ctx.stream_delta(
            self._stream_id,
            summary=summary,
            progress=progress,
            text=text,
            phase=self._phase,
        )

    async def _end(self):
        await self._ctx.stream_end(
            self._stream_id,
            summary=self.result,
            data=self.result_data,
        )
