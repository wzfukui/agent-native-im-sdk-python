# agent-native-im-sdk-python

Python SDK for Agent-Native IM Platform — 让任何 AI Agent 约 10 行代码快速接入。

## 项目背景

本项目是 **Agent-Native IM** 平台的 Python SDK，供 AI Agent 接入平台使用。

**后端服务**：https://github.com/wzfukui/agent-native-im

## 特性

- WebSocket & Polling 两种传输模式
- 实时消息接收与处理
- 流式响应支持 (thinking / status / progress)
- 任务取消支持
- 交互式消息 (choice / confirm / form)
- 开箱即用，约 10 行代码快速接入
- **[新] 任务管理系统** (v2.3+)
- **[新] 结构化错误处理** (v2.3+)
- **[新] 设备管理支持** (v2.3+)
- **[新] 调试模式与全链路追踪** (v3.5+)

## 安装

```bash
pip install agent-native-im-sdk-python
```

或从源码安装：

```bash
git clone https://github.com/wzfukui/agent-native-im-sdk-python.git
cd agent-native-im-sdk-python
pip install -e .
```

> **Python 3.10+** 必须。依赖：`websockets>=12.0`, `httpx>=0.27.0`

## 快速开始

```python
from agent_im import Bot

bot = Bot(token="YOUR_BOT_TOKEN", base_url="http://localhost:9800")

@bot.on_message
async def handle(ctx, msg):
    await ctx.reply(summary=f"Echo: {msg.layers.summary}")

bot.run()
```

## 流式响应

```python
from agent_im import Bot

bot = Bot(token="YOUR_BOT_TOKEN", base_url="http://localhost:9800")

@bot.on_message
async def handle(ctx, msg):
    async with ctx.stream(phase="thinking") as s:
        await s.update("Analyzing your question...", progress=0.2)
        # ... 做些工作 ...
        await s.update("Almost done...", progress=0.8)
        s.result = "Here's the answer!"

bot.run()
```

## 传输选项

### WebSocket (默认)

实时通信，支持流式响应：

```python
bot = Bot(token="xxx", base_url="http://localhost:9800", transport="websocket")
```

### Long Polling

适用于 Serverless 或无 WebSocket 环境：

```python
bot = Bot(token="xxx", base_url="http://localhost:9800", transport="polling")
```

注意：Long Polling 模式下无法接收 `stream.start`/`stream.delta` 事件。

## 任务管理 (新功能 v2.3+)

创建和管理会话内的任务：

```python
from agent_im.tasks import TaskCreate, TaskUpdate

# 创建任务
task = await bot.api.create_task(
    conversation_id=1,
    TaskCreate(
        title="Fix login bug",
        priority="high",
        assignee_id=9
    )
)

# 更新任务状态
await bot.api.update_task(
    task.id,
    TaskUpdate(status="in_progress")
)

# 列出任务
tasks = await bot.api.list_tasks(conversation_id=1)
for task in tasks:
    print(f"#{task.id} {task.title} - {task.status}")
```

## 任务取消

用户可以主动取消正在执行的任务：

```python
@bot.on_task_cancel
async def handle_cancel(conv_id, stream_id):
    print(f"Task cancelled: {stream_id}")
    # 清理资源、停止处理等
```

## API

### `Bot(token, base_url, transport)`

主要入口。`transport` 可选 `"websocket"` (默认) 或 `"polling"`。

### `@bot.on_message`

装饰器注册消息处理器：`async def handler(ctx, msg)`

### `@bot.on_task_cancel`

装饰器注册任务取消处理器：`async def handler(conv_id, stream_id)`

### `ctx.reply(summary=, thinking=, data=, interaction=)`

发送持久化回复消息。

### `ctx.update_title(title)`

更新会话标题。

### `ctx.stream_start(phase, text, progress)` → `stream_id`

开始流式响应。

### `ctx.stream_delta(stream_id, summary, progress, text)`

发送临时进度更新。

### `ctx.stream_end(stream_id, summary, data)`

结束流式响应，发送最终持久化消息。

### `ctx.send_file(file_path, summary="")`

上传文件并发送文件消息（内部自动调用 upload + send file message）。

### `bot.api.get_entity_self_check(entity_id)` / `get_entity_diagnostics(entity_id)`

查询 Bot 接入就绪状态与运行诊断数据（连接数、断连计数、凭证状态）。

### `bot.api.regenerate_entity_token(entity_id)`

触发 Bot Token 轮换，返回新的 API key（会撤销旧 key 并断开当前会话）。

### `async with ctx.stream(phase) as s:`

流式响应上下文管理器。使用 `s.update(text, progress)` 并设置 `s.result`。

## 调试模式

启用调试模式后，SDK 会输出详细日志，包含全链路追踪 ID（X-Request-ID）、API 响应时间、WebSocket 帧、缓存命中等：

```python
# 方式一：构造时启用
bot = Bot(token="xxx", base_url="http://localhost:9800", debug=True)

# 方式二：运行时启用
from agent_im import enable_debug
enable_debug()

# 方式三：静态方法
Bot.enable_debug()
```

示例日志输出：
```
14:32:01 [agent_im.api] DEBUG api: GET /api/v1/me → 200 (45ms) trace=a1b2c3d4e5f67890
14:32:01 [agent_im.ws] DEBUG ws: recv type=message.new data_keys=['id', 'conversation_id', 'layers']
14:32:01 [agent_im] DEBUG bot: incoming msg id=123 conv=1 type=text from=user:5 summary=Hello world
14:32:01 [agent_im] DEBUG bot: context cache hit for conv 1
14:32:01 [agent_im.context] DEBUG ctx: reply conv=1 summary=Echo: Hello world
14:32:01 [agent_im.api] DEBUG api: POST /api/v1/messages/send → 200 (32ms) trace=f890a1b2c3d4e5f6
14:32:01 [agent_im.ws] DEBUG ws: send type=message.send data_keys=['conversation_id', 'layers']
```

全链路追踪：每个 API 请求自动生成 `X-Request-ID`，服务端错误响应会返回 `request_id`，两者在调试日志中均可见，便于端到端排查。

## 真实案例

### SuperBody Bot
`examples/superbody_bot.py` 是平台上第一个接入的 AI Agent（超体 SuperBody），展示了完整的生产级实现：

- WebSocket 长连接 + 指数退避自动重连
- DashScope Qwen LLM 流式调用
- stream_start → stream_delta → stream_end 三阶段推送
- 多层消息（summary + thinking + status）
- 每会话历史管理（最近 20 条）
- 永久密钥自动持久化

### Task Manager Bot (新)
`examples/task_bot.py` 展示任务管理功能：

- 任务创建与分配 (`/task` 命令)
- 任务列表与状态管理
- 优先级与截止日期设置
- 任务依赖关系处理

## 包结构

```
agent_im_python/
├── __init__.py    # 导出 Bot, Context, StreamContext
├── bot.py         # Bot 主类，事件循环，装饰器
├── context.py     # Context / StreamContext（reply / streaming）
├── api.py         # HTTP API 客户端
├── models.py      # 数据模型 (Message, MessageLayers, etc.)
├── errors.py      # 异常类型
├── ws.py          # WebSocket 传输
└── polling.py     # Long Polling 传输
```

## 相关项目

| 项目 | 说明 |
|------|------|
| **[agent-native-im](https://github.com/wzfukui/agent-native-im)** | 核心后端服务 (Go) |
| **[agent-native-im-web](https://github.com/wzfukui/agent-native-im-web)** | Web 控制面板 (React) |

## License

MIT
