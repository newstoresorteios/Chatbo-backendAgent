from unittest.mock import MagicMock, patch

from app.services.conversas_service import ConversasService
from app.services.xnamai_outbound_service import XNamaiOutboundService


def test_xnamai_workspace_is_strictly_selected():
    service = XNamaiOutboundService()
    assert service.is_workspace("aa774d20-509f-4d54-865b-7a5de22b6d30") is True
    assert service.is_workspace("ns-workspace") is False
    assert service.is_workspace(None) is False


def test_xnamai_outbound_calls_dedicated_runtime_without_brevo():
    response = MagicMock()
    response.ok = True
    response.status_code = 200
    response.json.return_value = {"ok": True, "provider": "ycloud", "wamid": "wamid.1"}
    with (
        patch("app.services.xnamai_outbound_service.XNAMAI_AGENT_TOKEN", "shared-token"),
        patch("app.services.xnamai_outbound_service.requests.post", return_value=response) as post,
    ):
        result = XNamaiOutboundService().enviar_para_conversa(
            {"contact_phone": "whatsapp:558599498149"},
            "Ricardo: oi",
            correlation_id="message-1",
        )
    assert result == {"sent": True, "provider": "ycloud", "providerMessageId": "wamid.1"}
    assert post.call_args.args[0].endswith("/api/internal/chatbo/outbound")
    assert post.call_args.kwargs["json"]["workspaceId"] == "aa774d20-509f-4d54-865b-7a5de22b6d30"
    assert post.call_args.kwargs["json"]["recipient"] == "whatsapp:558599498149"


def test_conversation_service_routes_xnamai_to_ycloud_and_not_brevo():
    service = ConversasService()
    service.conversas = MagicMock()
    service.mensagens = MagicMock()
    service.usuarios = MagicMock()
    service.conversas.obter.return_value = {
        "id": "conversation-1",
        "workspace_id": "aa774d20-509f-4d54-865b-7a5de22b6d30",
        "channel": "whatsapp",
        "contact_phone": "whatsapp:558599498149",
        "status": "active",
        "assigned_to": "user-1",
    }
    service.mensagens.criar.return_value = {"id": "message-1"}
    service.mensagens.atualizar.return_value = {"id": "message-1", "status": "sent"}

    with (
        patch("app.services.meta_instagram_outbound.is_meta_instagram", return_value=False),
        patch("app.services.brevo_outbound_service.brevo_outbound_service") as brevo,
        patch("app.services.xnamai_outbound_service.xnamai_outbound_service") as ycloud,
        patch("app.services.human_takeover_bridge.mark_human_active"),
    ):
        brevo._lookup_inbound.return_value = {}
        ycloud.is_workspace.return_value = True
        ycloud.enviar_para_conversa.return_value = {"sent": True, "provider": "ycloud"}
        result = service.enviar_mensagem(
            "conversation-1",
            "oi",
            workspace_id="aa774d20-509f-4d54-865b-7a5de22b6d30",
            actor_user_id="user-1",
            actor_name="Ricardo",
        )

    assert result["status"] == "sent"
    ycloud.enviar_para_conversa.assert_called_once()
    brevo.enviar_para_conversa.assert_not_called()
