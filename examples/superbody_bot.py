"""SuperBody AI Bot — the first real agent on Agent-Native IM.

Connects via WebSocket, receives user messages, calls LLM (DashScope Qwen)
with streaming, and sends structured responses back through the IM platform.
"""

import asyncio
import json
import logging
import os
import uuid

import httpx
import websockets.asyncio.client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("superbody")

# --- Configuration ---
BOT_TOKEN = os.environ.get(
    "BOT_TOKEN",
    "aimb_550e655a95197b2efc3ff3078ee32abdaf9334dd0d1e68a8",
)
IM_SERVER = os.environ.get("IM_SERVER", "http://192.168.44.43:9800")
LLM_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "sk-971cc1a051d9468891101d85e3407ef2")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen3.5-plus")

# File to persist the permanent API key
KEY_FILE = os.path.join(os.path.dirname(__file__), ".superbody_key")

SYSTEM_PROMPT = """你是"超体 SuperBody"，上海雾帜智能科技有限公司的企业数字员工。
你运行在 Agent-Native IM 平台上——这是一款专为 AI 智能体设计的即时通讯系统。
你是这个平台上第一个接入的真正 AI Agent。

你的特点：
- 友好、专业、简洁
- 你了解 Agent-Native IM 的设计理念：平台只做投递不做理解，智能体是一等公民
- 你支持多层消息（summary/thinking/data/interaction）
- 你可以进行流式响应，用户能实时看到你的思考过程

请用中文回复，除非用户使用英文提问。"""

# Per-conversation message history
conversation_history: dict[int, list[dict]] = {}


def load_token() -> str:
    """Load permanent key if saved, otherwise use bootstrap key."""
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE) as f:
            key = f.read().strip()
            if key:
                logger.info("Using saved permanent key: %s...", key[:12])
                return key
    return BOT_TOKEN


def save_token(key: str):
    """Persist permanent API key to disk."""
    with open(KEY_FILE, "w") as f:
        f.write(key)
    logger.info("Permanent key saved to %s", KEY_FILE)


def ws_url(token: str) -> str:
    return IM_SERVER.replace("https://", "wss://").replace("http://", "ws://") + f"/api/v1/ws?token={token}"


async def verify_bot(token: str) -> dict | None:
    """Verify bot credentials against the IM server."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{IM_SERVER}/api/v1/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        data = resp.json()
        if data.get("ok"):
            return data["data"]
        logger.error("Bot verification failed: %s", data.get("error"))
        return None


async def update_subscriptions(token: str):
    """Update all conversation subscriptions to subscribe_all."""
    async with httpx.AsyncClient() as client:
        # List conversations
        resp = await client.get(
            f"{IM_SERVER}/api/v1/conversations",
            headers={"Authorization": f"Bearer {token}"},
        )
        data = resp.json()
        if not data.get("ok"):
            return

        for conv in data.get("data", []):
            conv_id = conv["id"]
            await client.put(
                f"{IM_SERVER}/api/v1/conversations/{conv_id}/subscription",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"mode": "subscribe_all"},
            )
            logger.info("Updated subscription for conversation %d to subscribe_all", conv_id)


async def call_llm_stream(conversation_id: int, user_message: str):
    """Call DashScope LLM with streaming, yield chunks."""
    history = conversation_history.get(conversation_id, [])
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *history[-20:],  # Keep last 20 messages
        {"role": "user", "content": user_message},
    ]

    async with httpx.AsyncClient() as client:
        async with client.stream(
            "POST",
            f"{LLM_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {LLM_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": LLM_MODEL,
                "messages": messages,
                "stream": True,
            },
            timeout=httpx.Timeout(120.0),
        ) as resp:
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                    delta = chunk["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue


async def handle_message(ws, msg_data: dict, bot_id: int):
    """Process an incoming message and respond with streaming LLM output."""
    sender_type = msg_data.get("sender_type", "")
    sender_id = msg_data.get("sender_id", 0)
    conversation_id = msg_data.get("conversation_id", 0)
    layers = msg_data.get("layers", {})
    user_text = layers.get("summary", "")

    # Skip own messages (regardless of sender_type) and empty messages
    if sender_id == bot_id:
        return
    if not user_text:
        return

    logger.info("[Conv %d] User: %s", conversation_id, user_text[:80])

    stream_id = uuid.uuid4().hex[:12]

    # --- stream.start ---
    await ws.send(json.dumps({
        "type": "message.send",
        "data": {
            "conversation_id": conversation_id,
            "stream_id": stream_id,
            "stream_type": "start",
            "layers": {
                "status": {"phase": "thinking", "progress": 0.0, "text": "正在思考..."},
            },
        },
    }))

    full_response = ""
    chunk_count = 0

    try:
        async for chunk in call_llm_stream(conversation_id, user_text):
            full_response += chunk
            chunk_count += 1

            # Send delta every 5 chunks
            if chunk_count % 5 == 0:
                progress = min(0.9, 0.1 + chunk_count * 0.005)
                await ws.send(json.dumps({
                    "type": "message.send",
                    "data": {
                        "conversation_id": conversation_id,
                        "stream_id": stream_id,
                        "stream_type": "delta",
                        "layers": {
                            "summary": full_response,
                            "status": {
                                "phase": "generating",
                                "progress": progress,
                                "text": f"生成中... {len(full_response)} 字",
                            },
                        },
                    },
                }))

    except Exception as e:
        logger.exception("LLM call failed")
        full_response = f"抱歉，处理请求时出错了：{e}"

    # --- stream.end (persisted) ---
    await ws.send(json.dumps({
        "type": "message.send",
        "data": {
            "conversation_id": conversation_id,
            "stream_id": stream_id,
            "stream_type": "end",
            "layers": {
                "summary": full_response,
                "thinking": f"使用 {LLM_MODEL} 生成，共 {len(full_response)} 字",
                "status": {"phase": "complete", "progress": 1.0, "text": "完成"},
            },
        },
    }))

    # Update history
    history = conversation_history.setdefault(conversation_id, [])
    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": full_response})
    if len(history) > 40:
        conversation_history[conversation_id] = history[-20:]

    logger.info("[Conv %d] Bot: %s", conversation_id, full_response[:80])


async def run():
    """Main event loop: connect, listen, respond."""
    token = load_token()

    # Verify bot first
    bot_info = await verify_bot(token)
    if not bot_info:
        logger.error("Cannot start: bot verification failed")
        return

    bot_id = bot_info["id"]
    bot_name = bot_info.get("display_name", bot_info.get("name", "unknown"))
    logger.info("Bot verified: %s (id=%d)", bot_name, bot_id)

    # Update subscriptions to receive all messages (not just @mentions)
    await update_subscriptions(token)

    # Connect WebSocket with auto-reconnect
    backoff = 1.0
    while True:
        try:
            async with websockets.asyncio.client.connect(
                ws_url(token),
                ping_interval=25,
                ping_timeout=60,
                max_size=256 * 1024,
                proxy=None,
            ) as ws:
                backoff = 1.0
                logger.info("WebSocket connected, listening for messages...")

                async for raw in ws:
                    try:
                        envelope = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    msg_type = envelope.get("type", "")
                    data = envelope.get("data", {})

                    if msg_type == "message.new":
                        asyncio.create_task(handle_message(ws, data, bot_id))
                    elif msg_type == "connection.approved":
                        api_key = data.get("api_key", "")
                        if api_key:
                            save_token(api_key)
                            token = api_key
                            await update_subscriptions(token)
                    elif msg_type == "error":
                        logger.warning("Server error: %s", data)

        except websockets.exceptions.ConnectionClosed as e:
            logger.warning("Connection closed: %s", e)
        except (OSError, websockets.exceptions.WebSocketException) as e:
            logger.warning("Connection error: %s", e)

        logger.info("Reconnecting in %.0fs...", backoff)
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 30.0)


if __name__ == "__main__":
    asyncio.run(run())
