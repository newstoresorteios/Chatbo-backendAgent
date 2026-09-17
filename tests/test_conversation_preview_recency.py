from unittest.mock import MagicMock, patch

from app.repositories.conversa_repository import ConversaRepository
from app.services.ai_conversas_bridge import AiConversasBridge


def repository_with_results(*results):
    repository = ConversaRepository()
    repository.obter = MagicMock(return_value={"id": "chat", "workspace_id": "ws"})
    query = MagicMock()
    query.update.return_value = query
    query.eq.return_value = query
    query.or_.return_value = query
    query.execute.side_effect = [MagicMock(data=rows) for rows in results]
    return repository, query


def test_old_ai_preview_cannot_replace_a_newer_human_message():
    current = {"id": "chat", "last_message": "Resposta humana", "last_message_at": "2026-09-16T15:00:00Z"}
    # A newer message can arrive after obter(), so the write must be conditional.
    repository, query = repository_with_results([], [current])
    with patch("app.repositories.conversa_repository.supabase") as db:
        db.table.return_value = query
        result = repository.atualizar("chat", {
            "last_message": "Resposta antiga da IA", "last_message_at": "2026-08-19T12:00:00Z",
            "customer_name": "Maria",
        }, workspace_id="ws", preserve_newer_preview=True)

    assert result == current
    query.or_.assert_called_once_with("last_message_at.is.null,last_message_at.lte.2026-08-19T12:00:00+00:00")
    fallback = query.update.call_args_list[1].args[0]
    assert fallback["customer_name"] == "Maria"
    assert "last_message_at" not in fallback and "last_message" not in fallback
    assert query.eq.call_args_list.count((("workspace_id", "ws"),)) == 2


def test_newer_preview_is_written_without_metadata_retry():
    latest = {"id": "chat", "last_message": "Nova resposta", "last_message_at": "2026-09-16T16:00:00-03:00"}
    repository, query = repository_with_results([latest])
    with patch("app.repositories.conversa_repository.supabase") as db:
        db.table.return_value = query
        assert repository.atualizar("chat", latest, workspace_id="ws", preserve_newer_preview=True) == latest
    query.update.assert_called_once()
    query.or_.assert_called_once_with("last_message_at.is.null,last_message_at.lte.2026-09-16T16:00:00-03:00")


def test_normal_conversation_updates_do_not_require_a_preview():
    repository, query = repository_with_results([{"id": "chat", "assigned_to": "operator"}])
    with patch("app.repositories.conversa_repository.supabase") as db:
        db.table.return_value = query
        result = repository.atualizar("chat", {"assigned_to": "operator"}, workspace_id="ws")
    assert result["assigned_to"] == "operator"
    query.or_.assert_not_called()


def test_both_ai_sync_paths_protect_preview_recency():
    bridge = AiConversasBridge()
    conversation = {"id": "chat", "workspace_id": "ws", "status": "active"}
    inbound = {"id": 1, "text": "Mensagem antiga", "created_at": "2026-08-19T12:00:00Z"}
    bridge.conversas = MagicMock()
    bridge._ensure_conversa = MagicMock(return_value=conversation)
    bridge._sync_thread_inbox("ws", "thread", [inbound], [], MagicMock())
    assert bridge.conversas.atualizar.call_args.kwargs["preserve_newer_preview"] is True
    bridge.conversas.reset_mock()
    bridge.mensagens = MagicMock()
    bridge.mensagens.listar_external_ids.return_value = {"ai-in-1"}
    bridge._load_thread_rows = MagicMock(return_value=([inbound], []))
    bridge.sync_messages_for_conversa(conversation, "ws")
    assert bridge.conversas.atualizar.call_args.kwargs["preserve_newer_preview"] is True
