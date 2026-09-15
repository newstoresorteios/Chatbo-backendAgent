from unittest.mock import MagicMock, patch

from app.repositories.conversa_repository import ConversaRepository
from app.repositories.mensagem_repository import MensagemRepository
from app.services.inbox_cache import invalidate_conversa


def _query_with_rows(rows: list[dict]) -> MagicMock:
    query = MagicMock()
    for method in ("select", "order", "range", "eq", "is_", "lt", "limit"):
        getattr(query, method).return_value = query
    query.execute.return_value = MagicMock(data=rows)
    return query


def test_conversation_list_limits_first_page_and_applies_cursor():
    query = _query_with_rows([{"id": "conv-1"}])
    with patch("app.repositories.conversa_repository.supabase") as mock_supabase:
        mock_supabase.table.return_value = query
        rows = ConversaRepository().listar(
            "workspace-1",
            max_rows=60,
            before="2026-09-14T12:00:00Z",
        )

    assert rows == [{"id": "conv-1"}]
    query.range.assert_called_once_with(0, 59)
    query.lt.assert_called_once_with("last_message_at", "2026-09-14T12:00:00Z")


def test_message_list_returns_latest_page_in_chronological_order():
    query = _query_with_rows(
        [
            {"id": "new", "created_at": "2026-09-14T12:00:00Z"},
            {"id": "old", "created_at": "2026-09-14T11:00:00Z"},
        ]
    )
    with patch("app.repositories.mensagem_repository.supabase") as mock_supabase:
        mock_supabase.table.return_value = query
        rows = MensagemRepository().listar_por_conversa("conv-1", limit=60)

    assert [row["id"] for row in rows] == ["old", "new"]
    query.order.assert_called_once_with("created_at", desc=True)
    query.limit.assert_called_once_with(60)


def test_invalidation_clears_every_cached_page():
    with patch("app.services.inbox_cache.mensagens_cache") as messages_cache, patch(
        "app.services.inbox_cache.conversas_cache"
    ) as conversations_cache:
        invalidate_conversa("conv-1", "workspace-1")

    messages_cache.delete_prefix.assert_called_once_with("mensagens:conv-1:")
    conversations_cache.delete_prefix.assert_called_once_with("conversas:workspace-1:")
