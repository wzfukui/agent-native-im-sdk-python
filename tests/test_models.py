from agent_im_python.models import _dict_to_message


def test_dict_to_message_parses_extended_fields():
    raw = {
        "id": 101,
        "conversation_id": 9,
        "stream_id": "abc123",
        "content_type": "file",
        "sender_type": "bot",
        "sender_id": 2,
        "attachments": [{"type": "file", "url": "/files/a.txt"}],
        "mentions": [1, 3],
        "mentioned_entity_ids": [3],
        "reply_to": 88,
        "reactions": [{"emoji": "👍", "count": 2}],
        "edited_at": "2026-03-06T12:00:00Z",
        "layers": {"summary": "done"},
        "created_at": "2026-03-06T11:59:00Z",
    }
    msg = _dict_to_message(raw)

    assert msg.id == 101
    assert msg.content_type == "file"
    assert msg.attachments[0]["type"] == "file"
    assert msg.mentions == [1, 3]
    assert msg.mentioned_entity_ids == [3]
    assert msg.reply_to == 88
    assert msg.reactions[0]["emoji"] == "👍"
    assert msg.edited_at == "2026-03-06T12:00:00Z"
