"""Test bot for Agent-Native IM - Simple echo with capabilities demonstration."""

import asyncio
import logging

from agent_native_im_sdk_python import Bot

logging.basicConfig(level=logging.INFO)

# 使用你的 bot token
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
BASE_URL = "http://192.168.44.43:9800"

bot = Bot(token=BOT_TOKEN, base_url=BASE_URL)


@bot.on_message
async def handle(ctx, msg):
    """Handle incoming messages with simple echo and capability demonstration."""
    user_message = msg.layers.summary or ""
    
    # Show thinking process
    async with ctx.stream(phase="thinking") as s:
        await s.update("Analyzing your message...", progress=0.2)
        await asyncio.sleep(0.5)
        
        await s.update("Processing...", progress=0.5)
        await asyncio.sleep(0.3)
        
        await s.update("Preparing response...", progress=0.8)
        await asyncio.sleep(0.2)
        
        # Final response
        s.result = f"🤖 Echo: {user_message}\n\nI received your message and responded via Agent-Native IM!"
        s.result_data = {
            "original_length": len(user_message),
            "processed": True
        }


@bot.on_task_cancel
async def handle_cancel(conv_id, stream_id):
    """Handle task cancellation."""
    print(f"⚠️ Task cancelled: conversation={conv_id}, stream={stream_id}")


if __name__ == "__main__":
    print(f"🤖 Starting test bot...")
    print(f"   Server: {BASE_URL}")
    print(f"   Token: {BOT_TOKEN[:20]}...")
    bot.run()
