from unittest.mock import MagicMock, patch

from app.services.ai_conversas_bridge import (
    _channel,
    _customer_display_name,
    _is_duplicate_external_id_error,
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


def test_display_name_prefers_instagram_username_over_contato():
    assert _customer_display_name(
        {"channel": "instagram", "sender_username": "tironi_oficial"},
        key="ig:12345664",
        existing="Contato 6664",
    ) == "tironi_oficial"


def test_display_name_keeps_good_existing_name():
    assert _customer_display_name(
        {"channel": "instagram"},
        key="ig:12345664",
        existing="Maria Silva",
    ) == "Maria Silva"


def test_is_duplicate_external_id_error():
    exc = Exception(
        'duplicate key value violates unique constraint "idx_mensagens_external_id_unique"'
        ' Key (external_id)=(ai-in-596) already exists.'
    )
    assert _is_duplicate_external_id_error(exc) is True
    assert _is_duplicate_external_id_error(Exception("connection timeout")) is False


def test_persist_message_skips_insert_when_external_id_exists_elsewhere():
    bridge = AiConversasBridge()
    bridge.mensagens = MagicMock()
    bridge.mensagens.obter_por_external_id.return_value = {
        "id": "msg-1",
        "conversa_id": "other-conversa",
        "external_id": "ai-in-596",
    }

    ok = bridge._persist_message(
        "conversa-atual",
        "ai-in-596",
        {"content": "oi", "sender": "customer"},
        "ws-1",
    )

    assert ok is True
    bridge.mensagens.criar.assert_not_called()
    bridge.mensagens.reatribuir_conversa.assert_called_once_with("msg-1", "conversa-atual")


def test_persist_message_treats_duplicate_key_as_noop():
    bridge = AiConversasBridge()
    bridge.mensagens = MagicMock()
    bridge.mensagens.obter_por_external_id.return_value = None
    bridge.mensagens.criar.side_effect = Exception(
        'duplicate key value violates unique constraint "idx_mensagens_external_id_unique"'
        ' Key (external_id)=(ai-in-596) already exists.'
    )

    ok = bridge._persist_message(
        "conversa-atual",
        "ai-in-596",
        {"content": "oi", "sender": "customer"},
        "ws-1",
    )

    assert ok is False
    bridge.mensagens.criar.assert_called_once()


def test_sync_messages_uses_global_external_id_check():
    bridge = AiConversasBridge()
    bridge.mensagens = MagicMock()
    bridge.mensagens.listar_external_ids.return_value = set()
    bridge._load_thread_rows = MagicMock(
        return_value=(
            [{"id": 596, "text": "oi", "created_at": "2026-08-01T10:00:00"}],
            [],
        )
    )
    bridge.conversas = MagicMock()

    with patch.object(bridge, "_upsert_inbound", return_value=False) as upsert:
        written = bridge.sync_messages_for_conversa(
            {"id": "conversa-1", "external_thread_id": "cv-1"},
            "ws-1",
        )

    assert written == 0
    upsert.assert_called_once()
    assert upsert.call_args.kwargs.get("known_new") is not True
