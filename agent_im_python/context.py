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
        memories: dict[str, str] | None = None,
        prompt: str = "",
    ):
        self.conversation_id = conversation_id
        self._api = api
        self._send_ws = send_ws_fn
        self.memories: dict[str, str] = memories or {}
        self.prompt: str = prompt

    # --- System context ---

    def get_system_context(self) -> str:
        """Build system context string from prompt + memories.

        Use this to inject conversation context into LLM system prompts::

            system = ctx.get_system_context() + "\\n\\n" + my_base_prompt
        """
        parts = []
        if self.prompt:
            parts.append(f"## Conversation Prompt\n{self.prompt}")
        if self.memories:
            mem_lines = [f"- {k}: {v}" for k, v in self.memories.items()]
            parts.append("## Conversation Memories\n" + "\n".join(mem_lines))
        return "\n\n".join(parts)

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

    # --- Reactions ---

    async def react(self, message_id: int, emoji: str) -> dict:
        """Toggle a reaction on a message in this conversation."""
        return await self._api.toggle_reaction(message_id, emoji)

    # --- Message editing ---

    async def edit_message(self, message_id: int, summary: str = "", data: Any = None) -> None:
        """Edit a previously sent message."""
        layers = MessageLayers(summary=summary, data=data)
        await self._api.edit_message(message_id, layers)

    # --- Structured mention ---

    async def mention(
        self,
        entity_ids: list[int],
        summary: str,
        intent_type: str = "task_assign",
        instruction: str = "",
        priority: str = "medium",
        context_refs: list[dict] | None = None,
    ) -> None:
        """Send a message with structured mention intent.

        intent_type: "task_assign", "question", "review", or "fyi"
        """
        data: dict[str, Any] = {
            "mention_intent": {
                "type": intent_type,
                "target_entities": entity_ids,
                "instruction": instruction or summary,
                "priority": priority,
            }
        }
        if context_refs:
            data["mention_intent"]["context_refs"] = context_refs

        layers = MessageLayers(summary=summary, data=data)
        await self._api.send_message(
            self.conversation_id,
            layers,
            mentions=entity_ids,
        )

    # --- Task handover ---

    async def handover(
        self,
        assign_to: list[int],
        summary: str,
        deliverables: list[dict[str, Any]] | None = None,
        task_id: int | None = None,
        handover_type: str = "task_completion",
        context: dict[str, Any] | None = None,
    ) -> None:
        """Send a structured task handover to other agents.

        handover_type: "task_completion", "bug_report", "review_request", "status_report"
        """
        handover_data: dict[str, Any] = {
            "handover_type": handover_type,
            "assign_to": assign_to,
        }
        if task_id is not None:
            handover_data["task_id"] = task_id
        if deliverables:
            handover_data["deliverables"] = deliverables
        if context:
            handover_data["context"] = context

        layers = MessageLayers(summary=summary, data=handover_data)
        await self._api.send_message(
            self.conversation_id,
            layers,
            content_type="task_handover",
            mentions=assign_to,
        )

    # --- Memory ---

    async def remember(self, key: str, content: str) -> dict:
        """Store a memory in this conversation (upsert by key)."""
        return await self._api.upsert_memory(self.conversation_id, key, content)

    async def recall(self, key: str | None = None) -> list[dict] | dict | None:
        """Recall memories. If key is given, find that specific memory; otherwise list all."""
        memories = await self._api.list_memories(self.conversation_id)
        if key is None:
            return memories
        for m in memories:
            if m.get("key") == key:
                return m
        return None

    async def forget(self, memory_id: int) -> None:
        """Delete a memory by ID."""
        await self._api.delete_memory(self.conversation_id, memory_id)

    # --- File upload ---

    async def upload_file(self, file_path: str) -> dict:
        """Upload a file and return its URL info."""
        return await self._api.upload_file(file_path)

    async def send_file(self, file_path: str, summary: str = "") -> None:
        """Upload and send a file message in the current conversation."""
        await self._api.send_file_message(self.conversation_id, file_path, summary=summary)

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
