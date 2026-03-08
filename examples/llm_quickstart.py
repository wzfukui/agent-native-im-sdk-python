"""Minimal LLM integration example — connect your bot to OpenAI in ~30 lines.

Usage:
    pip install agent-native-im-sdk-python openai
    export OPENAI_API_KEY=sk-...
    python llm_quickstart.py

Replace the token and base_url with your bot's credentials.
"""

import os
from agent_im_python import Bot

import openai

bot = Bot(
    token=os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN"),
    base_url=os.getenv("API_URL", "http://localhost:9800"),
    debug=True,
)

client = openai.AsyncOpenAI()


@bot.on_message
async def handle(ctx, msg):
    # Build system prompt from conversation context (memories + prompt)
    system = ctx.get_system_context()
    if not system:
        system = "You are a helpful AI assistant."

    # Stream the response so the user sees progress
    async with ctx.stream(phase="thinking") as s:
        await s.update("Thinking...", progress=0.2)

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": msg.layers.summary},
            ],
        )
        answer = response.choices[0].message.content or "Sorry, I couldn't generate a response."

        await s.update("Writing response...", progress=0.8)
        s.result = answer


bot.run()
