from app.services.ai_conversas_bridge import (
    _channel,
    _thread_key,
    AiConversasBridge,
)


def test_thread_key_prefers_conversation_id():
    assert _thread_key({
        "conversation_id": "brevo-abc",
        "sender_key": "whatsapp:5511999",
        "sender_phone": "5511999",
    }) == "brevo-abc"


def test_thread_key_falls_back_to_sender_key():
    assert _thread_key({
        "sender_key": "whatsapp:5511999",
        "sender_phone": "5511999",
    }) == "whatsapp:5511999"


def test_thread_key_ignores_blank():
    assert _thread_key({"conversation_id": "  ", "sender_key": None}) is None


def test_channel_normalizes_unknown():
    assert _channel({"channel": "whatsapp"}) == "whatsapp"
    assert _channel({"channel": "Instagram"}) == "instagram"
    assert _channel({"channel": "tiktok"}) == "whatsapp"


def test_group_threads_attaches_responses_via_inbound_id():
    bridge = AiConversasBridge()
    inbounds = [
        {
            "id": 10,
            "conversation_id": "cv-1",
            "sender_key": "whatsapp:5511",
            "created_at": "2026-08-01T10:00:00",
            "text": "oi",
        }
    ]
    responses = [
        {
            "id": 99,
            "inbound_id": 10,
            "sender_key": "whatsapp:5511",
            "created_at": "2026-08-01T10:00:05",
            "reply_text": "olá",
        }
    ]
    threads = bridge._group_threads(inbounds, responses)
    assert "cv-1" in threads
    assert len(threads["cv-1"]["inbounds"]) == 1
    assert len(threads["cv-1"]["responses"]) == 1
    assert "whatsapp:5511" not in threads


def test_group_threads_merges_orphan_response_by_sender_key():
    bridge = AiConversasBridge()
    inbounds = [
        {
            "id": 10,
            "conversation_id": "cv-1",
            "sender_key": "whatsapp:5511",
            "created_at": "2026-08-01T10:00:00",
            "text": "oi",
        }
    ]
    responses = [
        {
            "id": 99,
            "inbound_id": None,
            "sender_key": "whatsapp:5511",
            "created_at": "2026-08-01T10:00:05",
            "reply_text": "olá",
        }
    ]
    threads = bridge._group_threads(inbounds, responses)
    assert list(threads.keys()) == ["cv-1"]
    assert len(threads["cv-1"]["responses"]) == 1
