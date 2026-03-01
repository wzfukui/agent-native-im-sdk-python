"""Minimal echo bot — receives a message and replies with the same content."""

import logging

from agent_im import Bot

logging.basicConfig(level=logging.INFO)

bot = Bot(token="YOUR_BOT_TOKEN", base_url="http://localhost:9800")


@bot.on_message
async def handle(ctx, msg):
    text = msg.layers.summary or "(empty message)"
    await ctx.reply(summary=f"Echo: {text}")


if __name__ == "__main__":
    bot.run()
