"""High-level Agent framework for AI integration."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
from pathlib import Path
import asyncio

from .bot import Bot
from .models import Message, MessageLayers
from .context import Context


@dataclass
class AgentConfig:
    """Configuration for AI Agent behavior."""

    # Basic settings
    name: str = "AI Assistant"
    description: str = "A helpful AI assistant"
    version: str = "1.0.0"

    # Response behavior
    always_reply: bool = False  # If False, agent can choose not to reply
    reply_in_groups: bool = True  # Whether to reply in group conversations
    require_mention: bool = False  # Only reply when mentioned in groups

    # Context management
    max_history: int = 20  # Messages to keep in conversation history
    include_system_prompt: bool = True

    # Memory persistence
    memory_dir: Optional[str] = None  # Directory for persistent memory

    # LLM settings (for reference, actual LLM config is external)
    temperature: float = 0.7
    max_tokens: int = 2000
    model_name: str = "gpt-4"


@dataclass
class ConversationContext:
    """Manages conversation context and history."""

    conversation_id: int
    messages: List[Message] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_message(self, msg: Message, max_history: int = 20):
        """Add message to history, maintaining max size."""
        self.messages.append(msg)
        if len(self.messages) > max_history:
            self.messages = self.messages[-max_history:]

    def get_history_text(self) -> str:
        """Get formatted conversation history."""
        history = []
        for msg in self.messages:
            sender = "User" if msg.sender_type == "user" else "Bot"
            history.append(f"{sender}: {msg.layers.summary}")
        return "\n".join(history)

    def to_llm_messages(self) -> List[Dict[str, str]]:
        """Convert to LLM-compatible message format."""
        llm_messages = []
        for msg in self.messages:
            role = "user" if msg.sender_type == "user" else "assistant"
            content = msg.layers.summary
            if msg.layers.thinking:
                content += f"\n[Thinking: {msg.layers.thinking}]"
            llm_messages.append({"role": role, "content": content})
        return llm_messages


class NoReplySignal:
    """Special return value to indicate no reply should be sent."""
    pass


NO_REPLY = NoReplySignal()


class AIAgent:
    """High-level AI Agent with context management and memory."""

    def __init__(
        self,
        token: str,
        base_url: str,
        config: Optional[AgentConfig] = None,
        transport: str = "websocket",
    ):
        self.bot = Bot(token=token, base_url=base_url, transport=transport)
        self.config = config or AgentConfig()
        self.contexts: Dict[int, ConversationContext] = {}
        self.system_prompt: Optional[str] = None
        self.memory: Dict[str, Any] = {}

        # Load persistent memory if configured
        if self.config.memory_dir:
            self._load_memory()

        # Register handlers
        self.bot.on_message(self._handle_message)

    def set_system_prompt(self, prompt: str):
        """Set the system prompt for the AI."""
        self.system_prompt = prompt

    def set_skill(self, skill_data: Dict[str, Any]):
        """Set skill configuration from a skill file."""
        if "name" in skill_data:
            self.config.name = skill_data["name"]
        if "description" in skill_data:
            self.config.description = skill_data["description"]
        if "system_prompt" in skill_data:
            self.system_prompt = skill_data["system_prompt"]
        if "config" in skill_data:
            for key, value in skill_data["config"].items():
                if hasattr(self.config, key):
                    setattr(self.config, key, value)

    async def _handle_message(self, ctx: Context, msg: Message):
        """Internal message handler with context management."""
        conv_id = msg.conversation_id

        # Initialize or update context
        if conv_id not in self.contexts:
            self.contexts[conv_id] = ConversationContext(conv_id)

        context = self.contexts[conv_id]
        context.add_message(msg, self.config.max_history)

        # Check if we should respond
        should_respond = await self._should_respond(msg, context)
        if not should_respond:
            return  # Silently ignore

        # Process the message
        try:
            response = await self.process_message(msg, context)

            # Check for NO_REPLY signal
            if response is NO_REPLY:
                return  # Don't send any reply

            # Handle different response types
            if isinstance(response, str):
                await ctx.reply(summary=response)
            elif isinstance(response, MessageLayers):
                await ctx.reply(
                    summary=response.summary,
                    thinking=response.thinking,
                    data=response.data,
                    interaction=response.interaction
                )
            elif isinstance(response, dict):
                await ctx.reply(**response)

            # Save memory if configured
            if self.config.memory_dir:
                await self._save_memory()

        except Exception as e:
            # Error handling
            await ctx.reply(
                summary=f"Sorry, I encountered an error: {str(e)}",
                thinking=f"Error type: {type(e).__name__}"
            )

    async def _should_respond(self, msg: Message, context: ConversationContext) -> bool:
        """Determine if the agent should respond to this message."""
        # Always respond if configured to
        if self.config.always_reply:
            return True

        # In groups, check if we should reply
        is_group = context.metadata.get("is_group", False)
        if is_group:
            if not self.config.reply_in_groups:
                return False
            if self.config.require_mention:
                # Check if bot was mentioned
                bot_name = self.config.name.lower()
                message_lower = msg.layers.summary.lower()
                if bot_name not in message_lower and f"@{bot_name}" not in message_lower:
                    return False

        return True

    async def process_message(
        self,
        msg: Message,
        context: ConversationContext
    ) -> Union[str, MessageLayers, Dict, NoReplySignal]:
        """
        Process an incoming message and generate a response.

        Override this method in your agent implementation.
        Return NO_REPLY to skip sending a response.

        Args:
            msg: The incoming message
            context: Conversation context with history

        Returns:
            - str: Simple text response
            - MessageLayers: Rich response with thinking, data, etc.
            - dict: Kwargs for ctx.reply()
            - NO_REPLY: Signal to not send any response
        """
        # Default implementation - override this
        return f"Echo: {msg.layers.summary}"

    def _load_memory(self):
        """Load persistent memory from disk."""
        if not self.config.memory_dir:
            return

        memory_path = Path(self.config.memory_dir)
        memory_file = memory_path / "agent_memory.json"

        if memory_file.exists():
            with open(memory_file, "r") as f:
                self.memory = json.load(f)

    async def _save_memory(self):
        """Save memory to disk."""
        if not self.config.memory_dir:
            return

        memory_path = Path(self.config.memory_dir)
        memory_path.mkdir(parents=True, exist_ok=True)
        memory_file = memory_path / "agent_memory.json"

        with open(memory_file, "w") as f:
            json.dump(self.memory, f, indent=2, ensure_ascii=False)

    def remember(self, key: str, value: Any):
        """Store something in persistent memory."""
        self.memory[key] = value

    def recall(self, key: str, default: Any = None) -> Any:
        """Retrieve something from memory."""
        return self.memory.get(key, default)

    def get_context_for_llm(self, conversation_id: int) -> Dict[str, Any]:
        """Get formatted context for LLM calls."""
        context = self.contexts.get(conversation_id)
        if not context:
            return {}

        result = {
            "conversation_id": conversation_id,
            "history": context.get_history_text(),
            "messages": context.to_llm_messages(),
            "metadata": context.metadata,
            "memory": self.memory,
        }

        if self.config.include_system_prompt and self.system_prompt:
            result["system_prompt"] = self.system_prompt

        return result

    def run(self):
        """Start the agent."""
        self.bot.run()

    async def run_async(self):
        """Start the agent asynchronously."""
        await self.bot.run_async()


class StreamingAIAgent(AIAgent):
    """AI Agent with streaming response support."""

    async def process_message_streaming(
        self,
        ctx: Context,
        msg: Message,
        context: ConversationContext
    ) -> Union[NoReplySignal, None]:
        """
        Process message with streaming responses.

        Override this method for streaming implementations.
        Return NO_REPLY to skip sending a response.

        Example:
            async with ctx.stream(phase="thinking") as s:
                await s.update("Analyzing...", progress=0.3)
                # Process with LLM...
                await s.update("Generating response...", progress=0.7)
                s.result = "Final answer"
        """
        # Default implementation
        async with ctx.stream(phase="processing") as s:
            await s.update("Processing your message...", progress=0.5)
            response = await self.process_message(msg, context)
            if response is NO_REPLY:
                return NO_REPLY
            s.result = response if isinstance(response, str) else response.get("summary", "")

    async def _handle_message(self, ctx: Context, msg: Message):
        """Override to use streaming handler."""
        conv_id = msg.conversation_id

        # Initialize or update context
        if conv_id not in self.contexts:
            self.contexts[conv_id] = ConversationContext(conv_id)

        context = self.contexts[conv_id]
        context.add_message(msg, self.config.max_history)

        # Check if we should respond
        should_respond = await self._should_respond(msg, context)
        if not should_respond:
            return

        # Process with streaming
        try:
            result = await self.process_message_streaming(ctx, msg, context)
            if result is NO_REPLY:
                return

            # Save memory if configured
            if self.config.memory_dir:
                await self._save_memory()

        except Exception as e:
            await ctx.reply(
                summary=f"Sorry, I encountered an error: {str(e)}",
                thinking=f"Error type: {type(e).__name__}"
            )