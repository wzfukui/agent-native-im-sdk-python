# Agent-Native IM Python SDK API Reference

## Version: 2.3.0

Complete API reference for the Agent-Native IM Python SDK with v2.3+ features including task management, structured error handling, and device management.

## Table of Contents

1. [Installation](#installation)
2. [Quick Start](#quick-start)
3. [Bot Class](#bot-class)
4. [Context API](#context-api)
5. [Streaming API](#streaming-api)
6. [Task Management](#task-management)
7. [Error Handling](#error-handling)
8. [Models](#models)
9. [Transport Options](#transport-options)
10. [Advanced Usage](#advanced-usage)

---

## Installation

```bash
pip install agent-native-im-sdk-python
```

**Requirements:**
- Python 3.10+
- Dependencies: `websockets>=12.0`, `httpx>=0.27.0`

---

## Quick Start

### Basic Bot

```python
from agent_native_im_sdk_python import Bot

# Initialize bot with token
bot = Bot(
    token="YOUR_BOT_TOKEN",
    base_url="http://localhost:9800"
)

# Register message handler
@bot.on_message
async def handle_message(ctx, msg):
    await ctx.reply(summary=f"Echo: {msg.layers.summary}")

# Run the bot
bot.run()
```

### With Streaming Response

```python
@bot.on_message
async def handle_message(ctx, msg):
    async with ctx.stream(phase="thinking") as s:
        await s.update("Processing...", progress=0.3)
        # Do some work...
        await s.update("Almost done...", progress=0.8)
        s.result = "Here's the result!"
```

---

## Bot Class

### `Bot(token, base_url, transport="websocket", verbose=False)`

Main bot class for connecting to the Agent-Native IM platform.

**Parameters:**
- `token` (str): Bot authentication token
- `base_url` (str): API base URL
- `transport` (str): Transport method - "websocket" (default) or "polling"
- `verbose` (bool): Enable debug logging

**Methods:**

#### `bot.run()`
Start the bot and begin listening for messages.

#### `@bot.on_message`
Decorator to register message handler function.

```python
@bot.on_message
async def handler(ctx: Context, msg: Message):
    # Handle incoming message
    pass
```

#### `@bot.on_task_cancel`
Decorator to register task cancellation handler.

```python
@bot.on_task_cancel
async def handle_cancel(conversation_id: int, stream_id: str):
    # Clean up cancelled task
    pass
```

#### `bot.api`
Access to the low-level API client for direct API calls.

```python
# Get bot info
me = await bot.api.get_me()

# List conversations
conversations = await bot.api.list_conversations()
```

---

## Context API

The `Context` object is passed to message handlers and provides methods for responding to messages.

### Methods

#### `await ctx.reply(**kwargs)`
Send a persistent reply message.

**Parameters:**
- `summary` (str): Main message content (required)
- `thinking` (str, optional): Bot's reasoning/thinking process
- `status` (StatusLayer, optional): Status information
- `data` (dict, optional): Structured data payload
- `interaction` (Interaction, optional): Interactive elements

**Example:**
```python
await ctx.reply(
    summary="Task completed!",
    thinking="Analyzed the request and found the solution...",
    status=StatusLayer(
        text="Processing complete",
        icon="✅",
        progress=1.0
    )
)
```

#### `await ctx.update_title(title: str)`
Update the conversation title.

```python
await ctx.update_title("Bug Fix Discussion")
```

---

## Streaming API

For real-time progress updates and thinking visualization.

### Low-level Methods

#### `ctx.stream_start(phase, text, progress) -> stream_id`
Start a new stream.

#### `ctx.stream_delta(stream_id, summary, progress, text)`
Send stream update.

#### `ctx.stream_end(stream_id, summary, data)`
Finalize stream with persistent message.

### High-level Context Manager

#### `async with ctx.stream(phase) as s:`
Convenient streaming context manager.

**Parameters:**
- `phase` (str): Stream phase - "thinking", "planning", "executing", etc.

**Stream Object Methods:**
- `await s.update(text, progress)`: Send update
- `s.result`: Set final result (string or MessageLayers)

**Example:**
```python
@bot.on_message
async def handle(ctx, msg):
    async with ctx.stream(phase="analyzing") as s:
        await s.update("Reading documents...", progress=0.2)
        # Process documents...

        await s.update("Extracting information...", progress=0.5)
        # Extract data...

        await s.update("Generating response...", progress=0.8)
        # Generate result...

        s.result = MessageLayers(
            summary="Analysis complete!",
            thinking="Found 3 key insights from the documents...",
            data={"insights": ["insight1", "insight2", "insight3"]}
        )
```

---

## Task Management

v2.3+ introduces comprehensive task management within conversations.

### Creating Tasks

```python
from agent_native_im_sdk_python import TaskCreate

task = await bot.api.create_task(
    conversation_id=123,
    TaskCreate(
        title="Implement login feature",
        description="Add OAuth2 authentication",
        priority="high",  # low/medium/high
        assignee_id=456,  # Bot or user ID
        parent_task_id=None,  # For subtasks
        due_date="2024-01-15T00:00:00Z"
    )
)
```

### Listing Tasks

```python
tasks = await bot.api.list_tasks(conversation_id=123)

for task in tasks:
    print(f"Task #{task.id}: {task.title}")
    print(f"  Status: {task.status}")
    print(f"  Priority: {task.priority}")
    if task.is_blocked:
        print(f"  ⚠️ Blocked by parent task #{task.parent_task_id}")
    if task.is_overdue:
        print(f"  ⚠️ Overdue! Due: {task.due_date}")
```

### Updating Tasks

```python
from agent_native_im_sdk_python import TaskUpdate

# Update task properties
updated = await bot.api.update_task(
    task_id=789,
    TaskUpdate(
        status="in_progress",  # pending/in_progress/done/cancelled
        assignee_id=999,
        priority="urgent"
    )
)

# Convenience methods
await bot.api.start_task(task_id)     # Set status to "in_progress"
await bot.api.complete_task(task_id)  # Set status to "done"
await bot.api.cancel_task(task_id)    # Set status to "cancelled"
```

### Task Models

#### `Task`
```python
@dataclass
class Task:
    id: int
    conversation_id: int
    title: str
    description: str = ""
    priority: str = "medium"  # low/medium/high
    status: str = "pending"   # pending/in_progress/done/cancelled
    assignee_id: Optional[int] = None
    assignee: Optional[dict] = None  # Entity object
    parent_task_id: Optional[int] = None
    parent_task: Optional[Task] = None
    due_date: Optional[str] = None
    created_at: str
    updated_at: str

    @property
    def is_blocked(self) -> bool

    @property
    def is_overdue(self) -> bool
```

---

## Error Handling

v2.3+ introduces structured error responses with detailed error information.

### Error Types

#### `AgentIMError`
Base exception for all SDK errors.

#### `APIError`
API request errors with structured format.

```python
try:
    await bot.api.send_message(...)
except APIError as e:
    print(f"Error: {e.message}")
    print(f"Code: {e.code}")
    print(f"Status: {e.status_code}")
    print(f"Request ID: {e.request_id}")
    if e.details:
        print(f"Details: {e.details}")
```

#### `AuthenticationError`
Invalid or expired token (HTTP 401).

#### `ValidationError`
Request validation failed (HTTP 400).

```python
try:
    await bot.api.create_task(...)
except ValidationError as e:
    print(f"Field '{e.details['field']}' error: {e.message}")
```

#### `NotFoundError`
Resource not found (HTTP 404).

#### `ConflictError`
Resource conflict, e.g., duplicate (HTTP 409).

#### `RateLimitError`
Rate limit exceeded (HTTP 429).

```python
try:
    await bot.api.send_message(...)
except RateLimitError as e:
    retry_after = e.details.get('retry_after', 60)
    print(f"Rate limited. Retry after {retry_after} seconds")
    await asyncio.sleep(retry_after)
```

#### `ConnectionClosedError`
WebSocket connection lost unexpectedly.

### Error Response Format (v2.3+)

```json
{
  "ok": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid task priority",
    "status": 400,
    "request_id": "req_abc123",
    "details": {
      "field": "priority",
      "allowed": ["low", "medium", "high"]
    },
    "timestamp": "2024-01-01T00:00:00Z"
  }
}
```

---

## Models

### Message

```python
@dataclass
class Message:
    id: int
    conversation_id: int
    sender_id: int
    sender_type: str  # "user" or "bot"
    layers: MessageLayers
    created_at: str
    updated_at: str
    stream_id: str = ""
    is_stream_chunk: bool = False
```

### MessageLayers

```python
@dataclass
class MessageLayers:
    summary: str = ""
    thinking: str = ""
    status: Optional[StatusLayer] = None
    data: Optional[dict] = None
    artifacts: Optional[list[dict]] = None
    interaction: Optional[Interaction] = None
```

### StatusLayer

```python
@dataclass
class StatusLayer:
    text: str = ""
    icon: str = ""
    color: str = ""
    progress: float = 0.0
```

### Interaction

```python
@dataclass
class Interaction:
    type: str  # "choice", "confirm", "form"
    options: list[InteractionOption] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

@dataclass
class InteractionOption:
    label: str
    value: str
    icon: str = ""
```

### Conversation

```python
@dataclass
class Conversation:
    id: int
    user_id: int
    bot_id: int
    title: str
    created_at: str
    updated_at: str
```

---

## Transport Options

### WebSocket (Default)

Real-time bidirectional communication with streaming support.

```python
bot = Bot(
    token="xxx",
    base_url="http://localhost:9800",
    transport="websocket"
)
```

**Features:**
- Real-time message delivery
- Stream start/delta/end events
- Lower latency
- Automatic reconnection with exponential backoff

**Best for:**
- Interactive bots
- Real-time applications
- Streaming responses

### Long Polling

HTTP-based polling for environments without WebSocket support.

```python
bot = Bot(
    token="xxx",
    base_url="http://localhost:9800",
    transport="polling"
)
```

**Features:**
- Works in serverless environments
- Firewall-friendly
- No persistent connections

**Limitations:**
- No stream.start/delta events (only final messages)
- Higher latency
- More API calls

**Best for:**
- Serverless functions
- Restricted networks
- Simple request-response bots

---

## Advanced Usage

### Direct API Access

```python
# Get bot info
bot_info = await bot.api.get_me()

# List all conversations
conversations = await bot.api.list_conversations()

# Get message history
messages, has_more = await bot.api.list_messages(
    conversation_id=123,
    before=0,  # Message ID for pagination
    limit=50
)

# Send custom message
msg = await bot.api.send_message(
    conversation_id=123,
    layers=MessageLayers(
        summary="Custom message",
        data={"custom": "data"}
    ),
    stream_id="optional_stream_id"
)
```

### Interactive Messages

```python
from agent_native_im_sdk_python import Interaction, InteractionOption

await ctx.reply(
    summary="Choose an option:",
    interaction=Interaction(
        type="choice",
        options=[
            InteractionOption(label="Option A", value="a", icon="🅰️"),
            InteractionOption(label="Option B", value="b", icon="🅱️"),
            InteractionOption(label="Option C", value="c", icon="🆎")
        ]
    )
)
```

### Handling Multiple Conversations

```python
# Track conversation histories
histories = {}

@bot.on_message
async def handle(ctx, msg):
    conv_id = msg.conversation_id

    # Initialize history for new conversations
    if conv_id not in histories:
        histories[conv_id] = []

    # Add to history (keep last 20)
    histories[conv_id].append(msg)
    histories[conv_id] = histories[conv_id][-20:]

    # Process with context
    context = histories[conv_id]
    response = await process_with_context(msg, context)

    await ctx.reply(summary=response)
```

### Custom Error Recovery

```python
import asyncio
from agent_native_im_sdk_python import Bot, ConnectionClosedError

async def run_bot_with_recovery():
    while True:
        try:
            bot = Bot(token="xxx", base_url="xxx")

            @bot.on_message
            async def handle(ctx, msg):
                await ctx.reply(summary="Response")

            await bot.run_async()

        except ConnectionClosedError as e:
            print(f"Connection lost: {e}")
            await asyncio.sleep(5)  # Wait before reconnect

        except KeyboardInterrupt:
            print("Shutting down...")
            break

        except Exception as e:
            print(f"Unexpected error: {e}")
            await asyncio.sleep(10)

asyncio.run(run_bot_with_recovery())
```

### Device Management (v2.3+)

```python
# Future API for device management
# Note: Implementation pending backend support

# Register device
device = await bot.api.register_device(
    name="Bot Server #1",
    platform="linux",
    metadata={"version": "1.0.0"}
)

# List devices
devices = await bot.api.list_devices()

# Revoke device
await bot.api.revoke_device(device_id)
```

---

## Environment Variables

The SDK respects these environment variables:

- `AGENT_IM_TOKEN`: Bot token (overrides constructor parameter)
- `AGENT_IM_BASE_URL`: API base URL (overrides constructor parameter)
- `AGENT_IM_TRANSPORT`: Default transport ("websocket" or "polling")
- `AGENT_IM_VERBOSE`: Enable verbose logging ("true" or "1")

```python
import os

# Set via environment
os.environ['AGENT_IM_TOKEN'] = 'your_token'
os.environ['AGENT_IM_BASE_URL'] = 'https://api.example.com'

# Bot will use environment values
bot = Bot()  # No parameters needed
```

---

## Migration Guide

### From v2.2 to v2.3

1. **Error Handling**: Update error catching to use new error types
   ```python
   # Old
   try:
       await bot.api.send_message(...)
   except APIError as e:
       print(f"Error: {e}")

   # New
   try:
       await bot.api.send_message(...)
   except APIError as e:
       print(f"Error: {e.message} (Code: {e.code})")
       if e.request_id:
           print(f"Request ID for support: {e.request_id}")
   ```

2. **Task Management**: New feature, no migration needed
   ```python
   from agent_native_im_sdk_python import TaskCreate

   # Create tasks in conversations
   task = await bot.api.create_task(
       conversation_id=123,
       TaskCreate(title="New feature")
   )
   ```

3. **Device Management**: Coming soon in v2.4

---

## Troubleshooting

### Common Issues

#### WebSocket Connection Drops
- Check network stability
- Verify firewall rules allow WebSocket
- Consider using polling transport for unstable connections

#### Authentication Errors
- Verify token is correct
- Check token hasn't expired
- Ensure bot has necessary permissions

#### Rate Limiting
- Implement exponential backoff
- Cache responses when possible
- Use batch operations where available

#### Message Ordering
- Messages are guaranteed to be ordered within a conversation
- Use message IDs for deduplication
- Stream chunks have `is_stream_chunk=True`

### Debug Logging

Enable verbose mode for detailed logs:

```python
bot = Bot(token="xxx", base_url="xxx", verbose=True)

# Or via environment
os.environ['AGENT_IM_VERBOSE'] = 'true'
```

---

## Support

- GitHub Issues: [agent-native-im-sdk-python](https://github.com/wzfukui/agent-native-im-sdk-python/issues)
- Documentation: [Agent-Native IM Docs](https://github.com/wzfukui/agent-native-im)
- Examples: See `examples/` directory in the repository

---

## License

MIT License - See LICENSE file for details.