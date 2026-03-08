"""Tests for Bot initialization and configuration."""

import pytest

from agent_im_python.bot import Bot


def test_bot_init_stores_token_and_base_url():
    bot = Bot(token="test_token", base_url="http://localhost:9800")
    assert bot.token == "test_token"
    assert bot.base_url == "http://localhost:9800"


def test_bot_init_strips_trailing_slash():
    bot = Bot(token="t", base_url="http://localhost:9800/")
    assert bot.base_url == "http://localhost:9800"


def test_bot_init_default_transport_is_websocket():
    bot = Bot(token="t", base_url="http://localhost:9800")
    assert bot._transport_type == "websocket"


def test_bot_init_polling_transport():
    bot = Bot(token="t", base_url="http://localhost:9800", transport="polling")
    assert bot._transport_type == "polling"


def test_bot_on_message_registers_handler():
    bot = Bot(token="t", base_url="http://localhost:9800")

    @bot.on_message
    async def handler(ctx, msg):
        pass

    assert bot._handler is handler


def test_bot_on_task_cancel_registers_handler():
    bot = Bot(token="t", base_url="http://localhost:9800")

    @bot.on_task_cancel
    async def handler(conv_id, stream_id):
        pass

    assert bot._cancel_handler is handler


def test_bot_on_handover_registers_handler():
    bot = Bot(token="t", base_url="http://localhost:9800")

    @bot.on_handover
    async def handler(ctx, msg, data):
        pass

    assert bot._handover_handler is handler


def test_bot_key_file_disabled():
    bot = Bot(token="t", base_url="http://localhost:9800", key_file=None)
    assert bot._key_file is None
