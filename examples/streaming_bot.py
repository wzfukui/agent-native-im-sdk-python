"""Streaming bot — demonstrates the full stream lifecycle with progress updates."""

import asyncio
import logging

from agent_im import Bot

logging.basicConfig(level=logging.INFO)

bot = Bot(token="YOUR_BOT_TOKEN", base_url="http://localhost:9800")


@bot.on_message
async def handle(ctx, msg):
    question = msg.layers.summary or "nothing"

    # Use the stream context manager for clean lifecycle management
    async with ctx.stream(phase="thinking") as s:
        # Step 1: Analyze
        await s.update("Analyzing your question...", progress=0.2)
        await asyncio.sleep(1)  # simulate work

        # Step 2: Process
        await s.update("Processing data...", progress=0.5)
        await asyncio.sleep(1)

        # Step 3: Generate
        await s.update("Generating response...", progress=0.8)
        await asyncio.sleep(1)

        # Set the final result (persisted as stream.end)
        s.result = f"I processed your question: '{question}' — here's the answer!"
        s.result_data = {"input_length": len(question), "steps": 3}


if __name__ == "__main__":
    bot.run()
