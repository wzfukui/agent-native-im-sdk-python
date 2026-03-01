"""Async REST client wrapping all bot-accessible endpoints."""

from __future__ import annotations

from typing import Any

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


class APIClient:
    """Low-level async HTTP client for the Agent-Native IM API."""

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=httpx.Timeout(60.0),
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
            raise APIError(resp.status_code, body.get("error", "unknown error"))
        return body.get("data")

    # --- Bot endpoints ---

    async def get_me(self) -> Bot:
        d = await self._request("GET", "/api/v1/bot/me")
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
