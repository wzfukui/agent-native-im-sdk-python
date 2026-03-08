"""Async REST client wrapping all bot-accessible endpoints."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

import os

import httpx

from .errors import APIError, AuthenticationError

logger = logging.getLogger("agent_im.api")
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
        # Generate trace ID for full-chain tracing
        trace_id = uuid.uuid4().hex[:16]
        if "headers" not in kwargs:
            kwargs["headers"] = {}
        kwargs["headers"]["X-Request-ID"] = trace_id

        t0 = time.monotonic()
        resp = await self._client.request(method, path, **kwargs)
        elapsed_ms = (time.monotonic() - t0) * 1000

        try:
            body = resp.json()
        except ValueError:
            body = {"ok": False, "error": resp.text or f"HTTP {resp.status_code}"}

        # Extract server-assigned request ID if present
        server_req_id = ""
        if isinstance(body.get("error"), dict):
            server_req_id = body["error"].get("request_id", "")

        if resp.status_code >= 400:
            logger.debug(
                "api: %s %s → %d (%.0fms) trace=%s req=%s",
                method, path, resp.status_code, elapsed_ms,
                trace_id, server_req_id or "-",
            )
        else:
            logger.debug(
                "api: %s %s → %d (%.0fms) trace=%s",
                method, path, resp.status_code, elapsed_ms, trace_id,
            )

        if resp.status_code == 401:
            raise AuthenticationError()
        if resp.status_code == 204:
            return None
        if resp.status_code >= 400:
            raise APIError.from_response(resp.status_code, body)
        if not body.get("ok"):
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

    async def get_entity_self_check(self, entity_id: int) -> dict[str, Any]:
        """Get readiness diagnostics for one owned entity."""
        d = await self._request("GET", f"/api/v1/entities/{entity_id}/self-check")
        return d or {}

    async def get_entity_diagnostics(self, entity_id: int) -> dict[str, Any]:
        """Get runtime diagnostics for one owned entity."""
        d = await self._request("GET", f"/api/v1/entities/{entity_id}/diagnostics")
        return d or {}

    async def regenerate_entity_token(self, entity_id: int) -> dict[str, Any]:
        """Rotate one owned entity token and return new API key."""
        d = await self._request("POST", f"/api/v1/entities/{entity_id}/regenerate-token")
        return d or {}

    # --- Conversation endpoints ---

    async def list_conversations(self) -> list[Conversation]:
        data = await self._request("GET", "/api/v1/conversations")
        return [
            Conversation(
                id=c["id"],
                public_id=c.get("public_id", "") or ((c.get("metadata") or {}).get("public_id", "")),
                user_id=c.get("user_id", 0),
                bot_id=c.get("bot_id", 0),
                title=c.get("title", ""),
                metadata=c.get("metadata", {}) or {},
                created_at=c.get("created_at", ""),
                updated_at=c.get("updated_at", ""),
            )
            for c in data
        ]

    async def create_conversation(
        self,
        participant_ids: list[int],
        title: str = "",
        conv_type: str = "dm",
        description: str = "",
    ) -> Conversation:
        """Create a new conversation with the given participants.

        conv_type: "dm" for direct, "group" or "channel" for multi-party.
        The calling entity is automatically added as a participant.
        """
        payload: dict[str, Any] = {"participant_ids": participant_ids}
        if title:
            payload["title"] = title
        if conv_type != "dm":
            payload["conv_type"] = conv_type
        if description:
            payload["description"] = description
        d = await self._request("POST", "/api/v1/conversations", json=payload)
        return Conversation(
            id=d["id"],
            public_id=d.get("public_id", "") or ((d.get("metadata") or {}).get("public_id", "")),
            user_id=d.get("user_id", 0),
            bot_id=d.get("bot_id", 0),
            title=d.get("title", ""),
            metadata=d.get("metadata", {}) or {},
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
        )

    async def add_participant(
        self,
        conversation_id: int,
        entity_id: int,
        role: str = "member",
    ) -> dict[str, Any]:
        """Add a participant to an existing conversation."""
        d = await self._request(
            "POST",
            f"/api/v1/conversations/{conversation_id}/participants",
            json={"entity_id": entity_id, "role": role},
        )
        return d or {}

    async def update_conversation(self, conversation_id: int, title: str) -> Conversation:
        """Update a conversation's title."""
        d = await self._request(
            "PUT",
            f"/api/v1/conversations/{conversation_id}",
            json={"title": title},
        )
        return Conversation(
            id=d["id"],
            public_id=d.get("public_id", "") or ((d.get("metadata") or {}).get("public_id", "")),
            user_id=d.get("user_id", 0),
            bot_id=d.get("bot_id", 0),
            title=d.get("title", ""),
            metadata=d.get("metadata", {}) or {},
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
        )

    # --- Message endpoints ---

    async def send_message(
        self,
        conversation_id: int,
        layers: MessageLayers,
        stream_id: str = "",
        content_type: str = "",
        attachments: list[dict[str, Any]] | None = None,
        mentions: list[int] | None = None,
        reply_to: int | None = None,
    ) -> Message:
        payload: dict[str, Any] = {
            "conversation_id": conversation_id,
            "layers": _layers_to_dict(layers),
        }
        if stream_id:
            payload["stream_id"] = stream_id
        if content_type:
            payload["content_type"] = content_type
        if attachments:
            payload["attachments"] = attachments
        if mentions:
            payload["mentions"] = mentions
        if reply_to is not None:
            payload["reply_to"] = reply_to
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

    async def get_conversation_context(self, conversation_id: int) -> dict[str, Any]:
        """Get memories and prompt for a conversation.

        Returns {"memories": [...], "prompt": "..."}
        """
        d = await self._request("GET", f"/api/v1/conversations/{conversation_id}/memories")
        return {
            "memories": d.get("memories", []) if d else [],
            "prompt": d.get("prompt", "") if d else "",
        }

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

    # --- Entity search ---

    async def search_entities(self, capability: str) -> list[dict[str, Any]]:
        """Search for entities by capability.

        Searches metadata.capabilities.skills and metadata.tags.
        Returns list of entity dicts with 'online' status.
        """
        d = await self._request(
            "GET",
            "/api/v1/entities/search",
            params={"capability": capability},
        )
        return d if isinstance(d, list) else []

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

    async def send_file_message(
        self,
        conversation_id: int,
        file_path: str,
        summary: str = "",
        stream_id: str = "",
    ) -> Message:
        """Upload a file then send it as a file message."""
        uploaded = await self.upload_file(file_path)
        attachment = {
            "type": "file",
            "url": uploaded.get("url", ""),
            "filename": uploaded.get("filename", ""),
            "mime_type": uploaded.get("mime_type", ""),
            "size": uploaded.get("size", 0),
        }
        return await self.send_message(
            conversation_id=conversation_id,
            layers=MessageLayers(summary=summary),
            stream_id=stream_id,
            content_type="file",
            attachments=[attachment],
        )

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
