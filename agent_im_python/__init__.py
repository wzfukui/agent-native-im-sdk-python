"""agent-native-im-sdk-python: Python SDK for Agent-Native IM Platform."""

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
from .tasks import Task, TaskCreate, TaskUpdate
from .agent import AIAgent, StreamingAIAgent, AgentConfig, ConversationContext, NO_REPLY

def enable_debug():
    """Enable verbose debug logging for the entire SDK.

    Convenience shortcut for ``Bot.enable_debug()``.
    """
    Bot.enable_debug()

__all__ = [
    "Bot",
    "enable_debug",
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
    "Task",
    "TaskCreate",
    "TaskUpdate",
    "AIAgent",
    "StreamingAIAgent",
    "AgentConfig",
    "ConversationContext",
    "NO_REPLY",
]
