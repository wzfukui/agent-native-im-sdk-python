"""Data models mirroring the Go backend structs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StatusLayer:
    phase: str = ""
    progress: float = 0.0
    text: str = ""


@dataclass
class InteractionOption:
    label: str = ""
    value: str = ""


@dataclass
class Interaction:
    type: str = ""  # approval, choice, form
    prompt: str = ""
    options: list[InteractionOption] = field(default_factory=list)


@dataclass
class MessageLayers:
    thinking: str = ""
    status: StatusLayer | None = None
    data: Any = None
    summary: str = ""
    interaction: Interaction | None = None


@dataclass
class Message:
    id: int = 0
    conversation_id: int = 0
    stream_id: str = ""
    content_type: str = ""
    sender_type: str = ""  # "user" or "bot"
    sender_id: int = 0
    attachments: list[dict[str, Any]] = field(default_factory=list)
    mentions: list[int] = field(default_factory=list)
    mentioned_entity_ids: list[int] = field(default_factory=list)
    reply_to: int | None = None
    reactions: list[dict[str, Any]] = field(default_factory=list)
    edited_at: str = ""
    layers: MessageLayers = field(default_factory=MessageLayers)
    created_at: str = ""


    @property
    def mention_intent(self) -> dict | None:
        """Extract mention_intent from layers.data if present."""
        if isinstance(self.layers.data, dict):
            return self.layers.data.get("mention_intent")
        return None

    @property
    def is_handover(self) -> bool:
        """Check if this message is a task handover."""
        return self.content_type == "task_handover"


@dataclass
class Bot:
    id: int = 0
    owner_id: int = 0
    name: str = ""
    status: str = ""
    created_at: str = ""


@dataclass
class Conversation:
    id: int = 0
    public_id: str = ""
    user_id: int = 0
    bot_id: int = 0
    title: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


# --- Serialization helpers ---

def _layers_to_dict(layers: MessageLayers) -> dict:
    """Convert MessageLayers to dict, omitting None/empty values (like Go omitempty)."""
    d: dict[str, Any] = {}
    if layers.thinking:
        d["thinking"] = layers.thinking
    if layers.status is not None:
        s: dict[str, Any] = {"phase": layers.status.phase, "progress": layers.status.progress}
        if layers.status.text:
            s["text"] = layers.status.text
        d["status"] = s
    if layers.data is not None:
        d["data"] = layers.data
    if layers.summary:
        d["summary"] = layers.summary
    if layers.interaction is not None:
        inter: dict[str, Any] = {"type": layers.interaction.type}
        if layers.interaction.prompt:
            inter["prompt"] = layers.interaction.prompt
        if layers.interaction.options:
            inter["options"] = [{"label": o.label, "value": o.value} for o in layers.interaction.options]
        d["interaction"] = inter
    return d


def _dict_to_layers(d: dict | None) -> MessageLayers:
    """Parse a dict into MessageLayers."""
    if not d:
        return MessageLayers()
    layers = MessageLayers(
        thinking=d.get("thinking", ""),
        summary=d.get("summary", ""),
        data=d.get("data"),
    )
    if st := d.get("status"):
        layers.status = StatusLayer(
            phase=st.get("phase", ""),
            progress=st.get("progress", 0.0),
            text=st.get("text", ""),
        )
    if inter := d.get("interaction"):
        layers.interaction = Interaction(
            type=inter.get("type", ""),
            prompt=inter.get("prompt", ""),
            options=[InteractionOption(label=o["label"], value=o["value"]) for o in inter.get("options", [])],
        )
    return layers


def _dict_to_message(d: dict) -> Message:
    """Parse a dict into Message."""
    return Message(
        id=d.get("id", 0),
        conversation_id=d.get("conversation_id", 0),
        stream_id=d.get("stream_id", ""),
        content_type=d.get("content_type", ""),
        sender_type=d.get("sender_type", ""),
        sender_id=d.get("sender_id", 0),
        attachments=d.get("attachments", []) or [],
        mentions=d.get("mentions", []) or [],
        mentioned_entity_ids=d.get("mentioned_entity_ids", []) or [],
        reply_to=d.get("reply_to"),
        reactions=d.get("reactions", []) or [],
        edited_at=d.get("edited_at", ""),
        layers=_dict_to_layers(d.get("layers")),
        created_at=d.get("created_at", ""),
    )
