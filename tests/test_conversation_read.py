from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.providers.whatsapp_meta import WhatsAppMetaProvider
from app.repositories.conversa_repository import ConversaRepository
from app.services.conversas_service import ConversasService


def _conversation(**updates):
    return {
        "id": "conv-1", "workspace_id": "ws-1", "assigned_to": "user-1",
        "unread_count": 2, "channel": "whatsapp", "canal_id": "canal-1",
        **updates,
    }


def test_read_requires_workspace_and_assigned_operator():
    service = ConversasService()
    service.conversas = MagicMock()
    service.conversas.obter.return_value = _conversation()
    with pytest.raises(HTTPException) as missing:
        service.marcar_lida("conv-1", "user-1", "")
    assert missing.value.status_code == 400
    with pytest.raises(HTTPException) as forbidden:
        service.marcar_lida("conv-1", "other-user", "ws-1")
    assert forbidden.value.status_code == 403
    service.conversas.marcar_lida.assert_not_called()


def test_read_uses_conditional_count_and_queues_recent_meta_ack():
    service = ConversasService()
    service.conversas = MagicMock()
    service.mensagens = MagicMock()
    service.conversas.obter.return_value = _conversation()
    service.conversas.marcar_lida.return_value = _conversation(unread_count=0)
    service.mensagens.ultima_entrada_meta.return_value = {
        "external_id": "wamid.new",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    result, ack = service.marcar_lida("conv-1", "user-1", "ws-1")
    assert result["unreadCount"] == 0
    assert ack["message_id"] == "wamid.new"
    service.conversas.marcar_lida.assert_called_once_with("conv-1", "user-1", 2, "ws-1")


def test_read_does_not_ack_when_new_message_wins_race():
    service = ConversasService()
    service.conversas = MagicMock()
    service.mensagens = MagicMock()
    service.conversas.obter.side_effect = [_conversation(), _conversation(unread_count=3)]
    service.conversas.marcar_lida.return_value = None
    result, ack = service.marcar_lida("conv-1", "user-1", "ws-1")
    assert result["unreadCount"] == 3
    assert ack is None


def test_read_does_not_ack_message_older_than_meta_window():
    service = ConversasService()
    service.conversas = MagicMock()
    service.mensagens = MagicMock()
    service.conversas.obter.return_value = _conversation()
    service.conversas.marcar_lida.return_value = _conversation(unread_count=0)
    service.mensagens.ultima_entrada_meta.return_value = {
        "external_id": "wamid.old",
        "created_at": (datetime.now(timezone.utc) - timedelta(days=31)).isoformat(),
    }
    result, ack = service.marcar_lida("conv-1", "user-1", "ws-1")
    assert result["unreadCount"] == 0
    assert ack is None


def test_meta_ack_refuses_channel_from_another_workspace():
    with patch("app.services.whatsapp_service.whatsapp_service") as whatsapp:
        whatsapp.canais.get_canal.return_value = {"workspace_id": "ws-other"}
        ConversasService.confirmar_leitura_meta(_conversation(), "wamid.test")
    whatsapp._provider_for_canal.assert_not_called()


def test_read_repository_scopes_workspace_and_count():
    query = MagicMock()
    query.update.return_value = query
    query.eq.return_value = query
    query.execute.return_value = MagicMock(data=[_conversation(unread_count=0)])
    with patch("app.repositories.conversa_repository.supabase") as supabase:
        supabase.table.return_value = query
        result = ConversaRepository().marcar_lida("conv-1", "user-1", 2, "ws-1")
    assert result["unread_count"] == 0
    assert ("workspace_id", "ws-1") in [call.args for call in query.eq.call_args_list]
    assert ("unread_count", 2) in [call.args for call in query.eq.call_args_list]


def test_meta_read_payload_and_invalid_id():
    provider = WhatsAppMetaProvider(access_token="test", phone_number_id="123")
    response = MagicMock()
    response.json.return_value = {"success": True}
    with patch("app.providers.whatsapp_meta.requests.put", return_value=response) as put:
        assert provider.marcar_lida("wamid.test") == {"success": True}
    assert put.call_args.kwargs["json"] == {
        "messaging_product": "whatsapp", "status": "read", "message_id": "wamid.test",
    }
    with pytest.raises(ValueError):
        provider.marcar_lida("ai-in-123")
