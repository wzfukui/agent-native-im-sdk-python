"""agent-im: Python SDK for Agent-Native IM platform."""

from .bot import Bot
from .context import Context, StreamContext
from .models import (
    Bot as BotInfo,
    Conversation,
    Interaction,
    InteractionOption,
    Message,
    MessageLayers,
    StatusLayer,
)
from .errors import AgentIMError, APIError, AuthenticationError

__all__ = [
    "Bot",
    "BotInfo",
    "Context",
    "StreamContext",
    "Conversation",
    "Interaction",
    "InteractionOption",
    "Message",
    "MessageLayers",
    "StatusLayer",
    "AgentIMError",
    "APIError",
    "AuthenticationError",
]
