"""Comprehensive tests covering models, API, errors, context, ws, polling, and tasks."""

import asyncio
import json

import httpx
import pytest

from agent_im_python.models import (
    Message,
    MessageLayers,
    StatusLayer,
    Interaction,
    InteractionOption,
    _dict_to_message,
    _dict_to_layers,
    _layers_to_dict,
)
from agent_im_python.errors import (
    APIError,
    AuthenticationError,
    ValidationError,
    NotFoundError,
    RateLimitError,
)
from agent_im_python.api import APIClient
from agent_im_python.ws import WSTransport
from agent_im_python.polling import PollingTransport
from agent_im_python.tasks import Task, TaskCreate, TaskUpdate
from agent_im_python.context import Context, StreamContext


def run(coro):
    return asyncio.run(coro)


# --- Message model serialization/deserialization ---


class TestMessageSerialization:
    def test_layers_to_dict_omits_empty_fields(self):
        layers = MessageLayers(summary="hi")
        d = _layers_to_dict(layers)
        assert d == {"summary": "hi"}
        assert "thinking" not in d
        assert "status" not in d
        assert "data" not in d

    def test_layers_to_dict_includes_status(self):
        layers = MessageLayers(
            summary="done",
            status=StatusLayer(phase="complete", progress=1.0, text="All done"),
        )
        d = _layers_to_dict(layers)
        assert d["status"]["phase"] == "complete"
        assert d["status"]["progress"] == 1.0
        assert d["status"]["text"] == "All done"

    def test_layers_to_dict_includes_interaction(self):
        layers = MessageLayers(
            summary="Choose one",
            interaction=Interaction(
                type="choice",
                prompt="Pick:",
                options=[
                    InteractionOption(label="A", value="a"),
                    InteractionOption(label="B", value="b"),
                ],
            ),
        )
        d = _layers_to_dict(layers)
        assert d["interaction"]["type"] == "choice"
        assert len(d["interaction"]["options"]) == 2
        assert d["interaction"]["options"][0]["label"] == "A"

    def test_dict_to_layers_empty(self):
        layers = _dict_to_layers(None)
        assert layers.summary == ""
        assert layers.status is None

    def test_dict_to_layers_full(self):
        d = {
            "thinking": "hmm",
            "summary": "result",
            "data": {"key": "val"},
            "status": {"phase": "done", "progress": 1.0, "text": "ok"},
            "interaction": {
                "type": "approval",
                "prompt": "Approve?",
                "options": [{"label": "Yes", "value": "yes"}],
            },
        }
        layers = _dict_to_layers(d)
        assert layers.thinking == "hmm"
        assert layers.summary == "result"
        assert layers.data == {"key": "val"}
        assert layers.status.phase == "done"
        assert layers.interaction.type == "approval"
        assert layers.interaction.options[0].value == "yes"

    def test_message_is_mentioned(self):
        msg = Message(mentioned_entity_ids=[5, 10])
        assert msg.is_mentioned(5) is True
        assert msg.is_mentioned(99) is False

    def test_message_mention_intent(self):
        msg = Message(
            layers=MessageLayers(
                data={"mention_intent": {"type": "task_assign", "target_entities": [3]}}
            )
        )
        intent = msg.mention_intent
        assert intent is not None
        assert intent["type"] == "task_assign"

    def test_message_mention_intent_none_when_no_data(self):
        msg = Message()
        assert msg.mention_intent is None

    def test_message_is_handover(self):
        msg = Message(content_type="task_handover")
        assert msg.is_handover is True
        msg2 = Message(content_type="text")
        assert msg2.is_handover is False


# --- API client request building ---


class TestAPIClient:
    def test_request_adds_trace_id_header(self):
        captured_headers = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured_headers.update(dict(request.headers))
            return httpx.Response(200, json={"ok": True, "data": {}})

        client = APIClient("http://example.test", "mytoken")
        client._client = httpx.AsyncClient(
            base_url="http://example.test",
            transport=httpx.MockTransport(handler),
        )
        run(client._request("GET", "/api/v1/me"))
        assert "x-request-id" in captured_headers
        assert len(captured_headers["x-request-id"]) == 16
        run(client.close())

    def test_request_sets_auth_header(self):
        captured_headers = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured_headers.update(dict(request.headers))
            return httpx.Response(200, json={"ok": True, "data": {}})

        client = APIClient("http://example.test", "secret_token")
        client._client = httpx.AsyncClient(
            base_url="http://example.test",
            headers={"Authorization": "Bearer secret_token"},
            transport=httpx.MockTransport(handler),
        )
        run(client._request("GET", "/api/v1/me"))
        assert captured_headers["authorization"] == "Bearer secret_token"
        run(client.close())

    def test_update_token_changes_auth(self):
        client = APIClient("http://example.test", "old_token")
        client.update_token("new_token")
        assert client._client.headers["Authorization"] == "Bearer new_token"
        run(client.close())

    def test_request_raises_auth_error_on_401(self):
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"ok": False, "error": "unauthorized"})

        client = APIClient("http://example.test", "token")
        client._client = httpx.AsyncClient(
            base_url="http://example.test",
            transport=httpx.MockTransport(handler),
        )
        with pytest.raises(AuthenticationError):
            run(client._request("GET", "/api/v1/me"))
        run(client.close())

    def test_request_returns_none_on_204(self):
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(204)

        client = APIClient("http://example.test", "token")
        client._client = httpx.AsyncClient(
            base_url="http://example.test",
            transport=httpx.MockTransport(handler),
        )
        result = run(client._request("DELETE", "/api/v1/something"))
        assert result is None
        run(client.close())


# --- Error parsing ---


class TestErrorParsing:
    def test_api_error_from_structured_response(self):
        body = {
            "ok": False,
            "error": {
                "status": 404,
                "code": "ENTITY_NOT_FOUND",
                "message": "Entity not found",
                "request_id": "abc123",
                "details": {"entity_id": 99},
            },
        }
        err = APIError.from_response(404, body)
        assert err.status_code == 404
        assert err.code == "ENTITY_NOT_FOUND"
        assert err.message == "Entity not found"
        assert err.request_id == "abc123"
        assert err.details["entity_id"] == 99

    def test_api_error_from_legacy_response(self):
        body = {"ok": False, "error": "something went wrong"}
        err = APIError.from_response(500, body)
        assert err.status_code == 500
        assert err.message == "something went wrong"
        assert err.code == "UNKNOWN"

    def test_validation_error_fields(self):
        err = ValidationError("email", "invalid format", request_id="req1")
        assert err.status_code == 400
        assert err.code == "VALIDATION_ERROR"
        assert err.details["field"] == "email"

    def test_not_found_error(self):
        err = NotFoundError("conversation")
        assert err.status_code == 404
        assert "conversation not found" in err.message

    def test_rate_limit_error(self):
        err = RateLimitError(retry_after=30)
        assert err.status_code == 429
        assert err.details["retry_after"] == 30


# --- Streaming context lifecycle ---


class TestStreamContext:
    def test_stream_context_init(self):
        ctx = Context(conversation_id=1, api=None)
        sc = StreamContext(ctx, "thinking")
        assert sc._phase == "thinking"
        assert sc.result == ""
        assert sc.result_data is None


# --- Task models ---


class TestTaskModels:
    def test_task_from_dict(self):
        data = {
            "id": 42,
            "conversation_id": 1,
            "title": "Fix bug",
            "description": "Login page issue",
            "priority": "high",
            "status": "pending",
            "assignee_id": 5,
            "created_at": "2026-03-01T00:00:00Z",
        }
        task = Task.from_dict(data)
        assert task.id == 42
        assert task.title == "Fix bug"
        assert task.priority == "high"
        assert task.assignee_id == 5

    def test_task_is_overdue_false_when_no_due_date(self):
        task = Task(id=1, conversation_id=1, title="t")
        assert task.is_overdue is False

    def test_task_is_blocked_false_when_no_parent(self):
        task = Task(id=1, conversation_id=1, title="t")
        assert task.is_blocked is False

    def test_task_is_blocked_true_when_parent_pending(self):
        parent = Task(id=1, conversation_id=1, title="parent", status="pending")
        child = Task(id=2, conversation_id=1, title="child", parent_task=parent)
        assert child.is_blocked is True

    def test_task_is_blocked_false_when_parent_done(self):
        parent = Task(id=1, conversation_id=1, title="parent", status="done")
        child = Task(id=2, conversation_id=1, title="child", parent_task=parent)
        assert child.is_blocked is False

    def test_task_create_to_dict(self):
        tc = TaskCreate(
            title="Build feature",
            priority="high",
            assignee_id=3,
            due_date="2026-04-01T00:00:00Z",
        )
        d = tc.to_dict()
        assert d["title"] == "Build feature"
        assert d["priority"] == "high"
        assert d["assignee_id"] == 3
        assert d["due_date"] == "2026-04-01T00:00:00Z"

    def test_task_create_to_dict_minimal(self):
        tc = TaskCreate(title="Simple")
        d = tc.to_dict()
        assert d == {"title": "Simple", "priority": "medium"}

    def test_task_update_to_dict_partial(self):
        tu = TaskUpdate(status="done")
        d = tu.to_dict()
        assert d == {"status": "done"}
        assert "title" not in d

    def test_task_update_to_dict_empty(self):
        tu = TaskUpdate()
        d = tu.to_dict()
        assert d == {}


# --- WebSocket URL construction ---


class TestWSTransport:
    def test_ws_url_from_http(self):
        transport = WSTransport("http://localhost:9800", "mytoken")
        assert transport._url == "ws://localhost:9800/api/v1/ws?token=mytoken"

    def test_ws_url_from_https(self):
        transport = WSTransport("https://example.com", "mytoken")
        assert transport._url == "wss://example.com/api/v1/ws?token=mytoken"

    def test_ws_url_strips_trailing_slash(self):
        transport = WSTransport("http://localhost:9800/", "tok")
        assert transport._url == "ws://localhost:9800/api/v1/ws?token=tok"

    def test_ws_send_raises_when_not_connected(self):
        transport = WSTransport("http://localhost:9800", "tok")
        with pytest.raises(RuntimeError, match="not connected"):
            run(transport.send("test", {}))


# --- Polling transport ---


class TestPollingTransport:
    def test_stop_sets_running_false(self):
        client = APIClient("http://example.test", "token")
        transport = PollingTransport(client)
        transport._running = True
        transport.stop()
        assert transport._running is False
        run(client.close())


# --- Canonical import path ---


class TestCanonicalImport:
    def test_agent_im_imports_bot(self):
        from agent_im import Bot
        assert Bot is not None

    def test_agent_im_imports_context(self):
        from agent_im import Context, StreamContext
        assert Context is not None
        assert StreamContext is not None

    def test_agent_im_imports_errors(self):
        from agent_im import AgentIMError, APIError, AuthenticationError
        assert AgentIMError is not None

    def test_backward_compat_import(self):
        from agent_native_im_sdk_python import Bot
        assert Bot is not None
