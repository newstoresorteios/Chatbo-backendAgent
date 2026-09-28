from unittest.mock import MagicMock, patch

from app.services.conversas_service import ConversasService


def test_close_releases_human_and_reenables_agent_for_next_customer_message():
    service = ConversasService()
    service.conversas = MagicMock()
    service.mensagens = MagicMock()
    service.usuarios = MagicMock()
    current = {
        "id": "conversation-1",
        "workspace_id": "workspace-1",
        "status": "active",
        "assigned_to": "operator-1",
        "bot_activated": False,
    }
    closed = {**current, "status": "closed", "assigned_to": None, "bot_activated": True}
    service.conversas.obter.return_value = current
    service.conversas.atualizar.side_effect = [closed, closed]
    service.usuarios.listar.return_value = []

    with patch("app.services.inbox_cache.invalidate_conversa"):
        result = service.encerrar(
            "conversation-1", "Operador", workspace_id="workspace-1"
        )

    close_patch = service.conversas.atualizar.call_args_list[0].args[1]
    assert close_patch == {
        "status": "closed",
        "assigned_to": None,
        "bot_activated": True,
    }
    assert result["status"] == "closed"
    assert result["assignedTo"] is None
