"""Async REST client wrapping all bot-accessible endpoints."""

from __future__ import annotations

from typing import Any

import os

import httpx

from .errors import APIError, AuthenticationError
from .models import (
    Bot,
    Conversation,
    Message,
    MessageLayers,
    _dict_to_message,
    _layers_to_dict,
)
from .tasks import TaskMixin


class APIClient(TaskMixin):
    """Low-level async HTTP client for the Agent-Native IM API with task management."""

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=httpx.Timeout(60.0),
            trust_env=False,
        )

    async def close(self):
        await self._client.aclose()

    # --- Internal helpers ---

    async def _request(self, method: str, path: str, **kwargs) -> Any:
        resp = await self._client.request(method, path, **kwargs)
        if resp.status_code == 401:
            raise AuthenticationError()
        body = resp.json()
        if not body.get("ok"):
            # Use new structured error handling (v2.3+ compatible)
            raise APIError.from_response(resp.status_code, body)
        return body.get("data")

    # --- Bot endpoints ---

    async def get_me(self) -> Bot:
        d = await self._request("GET", "/api/v1/me")
        return Bot(
            id=d["id"],
            owner_id=d.get("owner_id", 0),
            name=d["name"],
            status=d.get("status", ""),
            created_at=d.get("created_at", ""),
        )

    # --- Conversation endpoints ---

    async def list_conversations(self) -> list[Conversation]:
        data = await self._request("GET", "/api/v1/conversations")
        return [
            Conversation(
                id=c["id"],
                user_id=c.get("user_id", 0),
                bot_id=c.get("bot_id", 0),
                title=c.get("title", ""),
                created_at=c.get("created_at", ""),
                updated_at=c.get("updated_at", ""),
            )
            for c in data
        ]

    async def update_conversation(self, conversation_id: int, title: str) -> Conversation:
        """Update a conversation's title."""
        d = await self._request(
            "PUT",
            f"/api/v1/conversations/{conversation_id}",
            json={"title": title},
        )
        return Conversation(
            id=d["id"],
            user_id=d.get("user_id", 0),
            bot_id=d.get("bot_id", 0),
            title=d.get("title", ""),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
        )

    # --- Message endpoints ---

    async def send_message(
        self,
        conversation_id: int,
        layers: MessageLayers,
        stream_id: str = "",
    ) -> Message:
        payload: dict[str, Any] = {
            "conversation_id": conversation_id,
            "layers": _layers_to_dict(layers),
        }
        if stream_id:
            payload["stream_id"] = stream_id
        d = await self._request("POST", "/api/v1/messages/send", json=payload)
        return _dict_to_message(d)

    async def list_messages(
        self,
        conversation_id: int,
        before: int = 0,
        limit: int = 20,
    ) -> tuple[list[Message], bool]:
        """Returns (messages, has_more)."""
        params: dict[str, Any] = {"limit": limit}
        if before:
            params["before"] = before
        d = await self._request(
            "GET",
            f"/api/v1/conversations/{conversation_id}/messages",
            params=params,
        )
        messages = [_dict_to_message(m) for m in d.get("messages", [])]
        return messages, d.get("has_more", False)

    # --- Reactions ---

    async def toggle_reaction(self, message_id: int, emoji: str) -> dict[str, Any]:
        """Toggle a reaction on a message (add if not exists, remove if exists).

        Returns dict with 'reactions' key containing updated reaction summaries.
        """
        d = await self._request(
            "POST",
            f"/api/v1/messages/{message_id}/reactions",
            json={"emoji": emoji},
        )
        return d

    # --- Message editing ---

    async def edit_message(self, message_id: int, layers: MessageLayers) -> Message:
        """Edit a previously sent message's layers."""
        d = await self._request(
            "PUT",
            f"/api/v1/messages/{message_id}",
            json={"layers": _layers_to_dict(layers)},
        )
        return _dict_to_message(d)

    # --- Memory ---

    async def list_memories(self, conversation_id: int) -> list[dict[str, Any]]:
        """List all memories for a conversation."""
        d = await self._request("GET", f"/api/v1/conversations/{conversation_id}/memories")
        return d.get("memories", []) if d else []

    async def upsert_memory(self, conversation_id: int, key: str, content: str) -> dict[str, Any]:
        """Create or update a memory by key."""
        d = await self._request(
            "POST",
            f"/api/v1/conversations/{conversation_id}/memories",
            json={"key": key, "content": content},
        )
        return d

    async def delete_memory(self, conversation_id: int, memory_id: int) -> None:
        """Delete a memory by ID."""
        await self._request("DELETE", f"/api/v1/conversations/{conversation_id}/memories/{memory_id}")

    # --- File upload ---

    async def upload_file(self, file_path: str) -> dict[str, Any]:
        """Upload a file from disk. Returns dict with 'url', 'filename', 'size'."""
        filename = os.path.basename(file_path)
        with open(file_path, "rb") as f:
            d = await self._request(
                "POST",
                "/api/v1/files/upload",
                files={"file": (filename, f)},
            )
        return d

    async def upload_file_content(self, filename: str, content: bytes, mime_type: str = "application/octet-stream") -> dict[str, Any]:
        """Upload file content directly. Returns dict with 'url', 'filename', 'size'."""
        d = await self._request(
            "POST",
            "/api/v1/files/upload",
            files={"file": (filename, content, mime_type)},
        )
        return d

    # --- Long polling ---

    async def get_updates(self, offset: int = 0, timeout: int = 30) -> list[Message]:
        d = await self._request(
            "GET",
            "/api/v1/updates",
            params={"offset": offset, "timeout": timeout},
        )
        if d is None:
            return []
        return [_dict_to_message(m) for m in d]
