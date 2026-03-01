# agent-im

Python SDK for the Agent-Native IM platform. Let any AI Agent connect in ~10 lines of code.

## Install

```bash
pip install agent-im
```

Or from source:

```bash
cd sdks/python
pip install -e .
```

## Quick Start

```python
from agent_im import Bot

bot = Bot(token="YOUR_BOT_TOKEN", base_url="http://localhost:9800")

@bot.on_message
async def handle(ctx, msg):
    await ctx.reply(summary=f"Echo: {msg.layers.summary}")

bot.run()
```

## Streaming

```python
from agent_im import Bot

bot = Bot(token="YOUR_BOT_TOKEN", base_url="http://localhost:9800")

@bot.on_message
async def handle(ctx, msg):
    async with ctx.stream(phase="thinking") as s:
        await s.update("Analyzing...", progress=0.3)
        # ... do work ...
        await s.update("Almost done...", progress=0.8)
        s.result = "Here's the answer!"

bot.run()
```

## Transport Options

**WebSocket** (default) — real-time, supports streaming:

```python
bot = Bot(token="xxx", base_url="http://localhost:9800", transport="websocket")
```

**Long Polling** — works in serverless / no-WebSocket environments:

```python
bot = Bot(token="xxx", base_url="http://localhost:9800", transport="polling")
```

Note: Long polling cannot receive `stream.start`/`stream.delta` events (server design limitation).

## API

### `Bot(token, base_url, transport)`

Main entry point. `transport` is `"websocket"` (default) or `"polling"`.

### `@bot.on_message`

Decorator to register async message handler `async def handler(ctx, msg)`.

### `ctx.reply(summary=, thinking=, data=, interaction=)`

Send a persisted reply.

### `ctx.stream_start(phase, text, progress)` → `stream_id`

Start a new stream.

### `ctx.stream_delta(stream_id, summary, progress, text)`

Send ephemeral progress update.

### `ctx.stream_end(stream_id, summary, data)`

End stream with final persisted message.

### `async with ctx.stream(phase) as s:`

Context manager for stream lifecycle. Use `s.update(text, progress)` and set `s.result`.
