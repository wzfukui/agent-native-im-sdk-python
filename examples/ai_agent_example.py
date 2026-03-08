#!/usr/bin/env python3
"""
Advanced AI Agent example with LLM integration, memory, and selective responses.

This example shows how to:
1. Create an AI agent with memory and context
2. Integrate with LLMs (OpenAI, Anthropic, etc.)
3. Choose when to respond or ignore messages
4. Handle group conversations intelligently
5. Persist memory across restarts
"""

import asyncio
import os
from typing import Union

# Example with OpenAI (can be replaced with any LLM)
import openai
from agent_im import (
    AIAgent,
    AgentConfig,
    ConversationContext,
    Message,
    MessageLayers,
    NO_REPLY
)


class SmartAssistant(AIAgent):
    """An intelligent assistant that knows when to respond."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Set system prompt for the AI
        self.set_system_prompt("""
You are a helpful AI assistant integrated into the Agent-Native IM platform.

Key behaviors:
1. Only respond when the message is directed at you or needs your help
2. In groups, only respond when mentioned or when the topic is relevant
3. Return NO_REPLY for messages you should ignore (casual chat, off-topic)
4. Remember important information about users and conversations
5. Provide thoughtful, contextual responses
        """)

        # Initialize OpenAI
        openai.api_key = os.getenv("OPENAI_API_KEY")

    async def process_message(
        self,
        msg: Message,
        context: ConversationContext
    ) -> Union[str, MessageLayers, NO_REPLY]:
        """Process message with LLM and decide whether to respond."""

        user_message = msg.layers.summary

        # Quick filters for messages we should ignore
        ignore_patterns = [
            "hello", "hi", "hey",  # Simple greetings between users
            "ok", "okay", "sure",  # Acknowledgments
            "thanks", "thx", "ty",  # Simple thanks
        ]

        # Check if this is a simple message we should ignore
        if len(user_message.split()) <= 2 and any(
            pattern in user_message.lower() for pattern in ignore_patterns
        ):
            # Check if it's directed at us
            if self.config.name.lower() not in user_message.lower():
                return NO_REPLY

        # Get conversation context for LLM
        llm_context = self.get_context_for_llm(msg.conversation_id)

        # Prepare messages for LLM
        messages = [
            {"role": "system", "content": self.system_prompt}
        ]

        # Add conversation history
        messages.extend(llm_context.get("messages", []))

        # Add decision prompt
        messages.append({
            "role": "system",
            "content": """
Based on the conversation, decide:
1. Should you respond? (Consider relevance, whether you're being addressed, etc.)
2. If yes, what's your response?
3. What should you remember from this conversation?

If you should NOT respond, start your response with "NO_REPLY:"
If you should respond, start with "REPLY:" followed by your response.
Include any important information to remember after "REMEMBER:"
            """
        })

        # Call LLM
        try:
            response = await self._call_llm(messages)

            # Parse LLM response
            if response.startswith("NO_REPLY:"):
                # Extract any memory updates
                self._extract_memory(response)
                return NO_REPLY

            elif response.startswith("REPLY:"):
                # Extract the actual reply
                reply_text = response.replace("REPLY:", "").strip()

                # Extract memory updates
                self._extract_memory(response)

                # Split out any thinking process
                if "[THINKING:" in reply_text:
                    parts = reply_text.split("[THINKING:")
                    summary = parts[0].strip()
                    thinking = parts[1].replace("]", "").strip() if len(parts) > 1 else ""

                    return MessageLayers(
                        summary=summary,
                        thinking=thinking
                    )
                else:
                    return reply_text

            else:
                # Default to replying if LLM didn't follow format
                return response

        except Exception as e:
            # On error, be transparent
            return MessageLayers(
                summary="I encountered an error processing your message.",
                thinking=f"Error: {str(e)}"
            )

    async def _call_llm(self, messages):
        """Call the LLM API (OpenAI in this example)."""
        try:
            response = await openai.ChatCompletion.acreate(
                model="gpt-4",
                messages=messages,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens
            )
            return response.choices[0].message.content

        except Exception as e:
            print(f"LLM API error: {e}")
            raise

    def _extract_memory(self, response: str):
        """Extract and store memory items from LLM response."""
        if "REMEMBER:" in response:
            memory_section = response.split("REMEMBER:")[1].strip()
            lines = memory_section.split("\n")

            for line in lines:
                if ":" in line:
                    key, value = line.split(":", 1)
                    key = key.strip()
                    value = value.strip()
                    if key and value:
                        self.remember(key, value)


class StreamingSmartAssistant(SmartAssistant):
    """Version with streaming responses for better UX."""

    async def process_message_streaming(
        self,
        ctx,
        msg: Message,
        context: ConversationContext
    ) -> Union[NO_REPLY, None]:
        """Process with streaming for real-time feedback."""

        # First, check if we should respond
        user_message = msg.layers.summary

        # Quick check for ignore patterns
        ignore_patterns = ["hello", "hi", "ok", "sure", "thanks"]
        if len(user_message.split()) <= 2 and any(
            p in user_message.lower() for p in ignore_patterns
        ):
            if self.config.name.lower() not in user_message.lower():
                return NO_REPLY

        # Stream the response
        async with ctx.stream(phase="thinking") as s:
            await s.update("Analyzing your message...", progress=0.2)

            # Get LLM context
            llm_context = self.get_context_for_llm(msg.conversation_id)
            await s.update("Retrieving context...", progress=0.4)

            # Prepare and call LLM
            messages = self._prepare_llm_messages(llm_context, user_message)
            await s.update("Generating response...", progress=0.6)

            try:
                response = await self._call_llm(messages)
                await s.update("Finalizing...", progress=0.9)

                # Parse response
                if response.startswith("NO_REPLY:"):
                    self._extract_memory(response)
                    return NO_REPLY

                elif response.startswith("REPLY:"):
                    reply_text = response.replace("REPLY:", "").strip()
                    self._extract_memory(response)

                    # Set the final result
                    if "[THINKING:" in reply_text:
                        parts = reply_text.split("[THINKING:")
                        s.result = parts[0].strip()
                        # thinking goes in metadata
                        s.result_data = {
                            "thinking": parts[1].replace("]", "").strip()
                        }
                    else:
                        s.result = reply_text

                else:
                    s.result = response

            except Exception as e:
                s.result = "I encountered an error processing your message."
                s.result_data = {"error": str(e)}

    def _prepare_llm_messages(self, llm_context, user_message):
        """Prepare messages for LLM call."""
        messages = [
            {"role": "system", "content": self.system_prompt}
        ]
        messages.extend(llm_context.get("messages", []))
        messages.append({
            "role": "system",
            "content": "Decide if you should respond (NO_REPLY:) or provide a response (REPLY:)"
        })
        return messages


# Example skill configuration file content
SKILL_TEMPLATE = """
{
  "name": "SmartAssistant",
  "version": "1.0.0",
  "description": "An intelligent AI assistant that knows when to respond",
  "author": "Your Name",

  "system_prompt": "You are a helpful AI assistant. Be concise, accurate, and friendly.",

  "config": {
    "always_reply": false,
    "reply_in_groups": true,
    "require_mention": true,
    "max_history": 30,
    "temperature": 0.7,
    "max_tokens": 2000,
    "model_name": "gpt-4"
  },

  "triggers": {
    "keywords": ["help", "assist", "question", "how to", "what is", "explain"],
    "patterns": ["@bot", "!ai", "/ask"],
    "commands": ["/help", "/search", "/summarize"]
  },

  "capabilities": [
    "answer_questions",
    "provide_code_examples",
    "explain_concepts",
    "summarize_text",
    "translate_languages"
  ],

  "memory_schema": {
    "user_preferences": {},
    "conversation_topics": [],
    "learned_facts": {},
    "task_history": []
  }
}
"""


async def main():
    """Main entry point."""

    # Load configuration
    config = AgentConfig(
        name="SmartBot",
        description="An AI that knows when to respond",
        always_reply=False,  # Don't always reply
        reply_in_groups=True,  # Can reply in groups
        require_mention=False,  # Don't require @ mention
        max_history=30,
        memory_dir="./agent_memory"  # Persist memory
    )

    # Create agent
    agent = StreamingSmartAssistant(
        token=os.getenv("BOT_TOKEN"),
        base_url="http://localhost:9800",
        config=config
    )

    # Load skill file if exists
    skill_file = "./smart_assistant.skill.json"
    if os.path.exists(skill_file):
        import json
        with open(skill_file) as f:
            skill_data = json.load(f)
            agent.set_skill(skill_data)
            print(f"Loaded skill: {skill_data['name']} v{skill_data['version']}")

    # Run the agent
    print(f"Starting {config.name}...")
    print(f"Memory directory: {config.memory_dir}")
    print(f"Selective responses: enabled")
    print(f"Group replies: {config.reply_in_groups}")

    await agent.run_async()


if __name__ == "__main__":
    # Run with auto-restart for resilience
    while True:
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            print("\nShutting down...")
            break
        except Exception as e:
            print(f"Error: {e}")
            print("Restarting in 5 seconds...")
            import time
            time.sleep(5)