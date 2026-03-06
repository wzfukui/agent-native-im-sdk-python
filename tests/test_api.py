import asyncio

import httpx
import pytest

from agent_im_python.api import APIClient
from agent_im_python.errors import APIError


def run(coro):
    return asyncio.run(coro)


def test_request_handles_non_json_error_response():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="bad gateway")

    client = APIClient("http://example.test", "token")
    client._client = httpx.AsyncClient(
        base_url="http://example.test",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(APIError) as err:
        run(client._request("GET", "/api/v1/me"))

    assert err.value.status_code == 502
    assert "bad gateway" in err.value.message.lower()
    run(client.close())


def test_list_conversations_parses_public_id_from_metadata():
    def handler(_request: httpx.Request) -> httpx.Response:
        body = {
            "ok": True,
            "data": [
                {
                    "id": 1,
                    "title": "Demo",
                    "metadata": {"public_id": "9ed5d8d2-5a70-4f6c-af7f-55f6e5f9e29f"},
                }
            ],
        }
        return httpx.Response(200, json=body)

    client = APIClient("http://example.test", "token")
    client._client = httpx.AsyncClient(
        base_url="http://example.test",
        transport=httpx.MockTransport(handler),
    )

    conversations = run(client.list_conversations())
    assert conversations[0].public_id == "9ed5d8d2-5a70-4f6c-af7f-55f6e5f9e29f"
    run(client.close())


def test_entity_ops_paths():
    called = {"path": ""}

    def handler(request: httpx.Request) -> httpx.Response:
        called["path"] = request.url.path
        return httpx.Response(200, json={"ok": True, "data": {"entity_id": 7}})

    client = APIClient("http://example.test", "token")
    client._client = httpx.AsyncClient(
        base_url="http://example.test",
        transport=httpx.MockTransport(handler),
    )

    run(client.get_entity_self_check(7))
    assert called["path"] == "/api/v1/entities/7/self-check"

    run(client.get_entity_diagnostics(7))
    assert called["path"] == "/api/v1/entities/7/diagnostics"

    run(client.regenerate_entity_token(7))
    assert called["path"] == "/api/v1/entities/7/regenerate-token"
    run(client.close())
