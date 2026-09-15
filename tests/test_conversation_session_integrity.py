from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.ai_conversas_bridge import AiConversasBridge


class Query:
    def __init__(self, rows):
        self.rows = list(rows)
    def select(self, *_a, **_k): return self
    def eq(self, key, value):
        self.rows = [r for r in self.rows if r.get(key) == value]
        return self
    def in_(self, key, values):
        self.rows = [r for r in self.rows if str(r.get(key)) in values]
        return self
    def order(self, *_a, **_k): return self
    def limit(self, limit):
        self.rows = self.rows[:limit]
        return self
    def range(self, start, end):
        self.rows = self.rows[start:end+1]
        return self
    def execute(self): return SimpleNamespace(data=self.rows)


def test_open_thread_never_collects_other_sessions_or_workspaces(monkeypatch):
    rows = {
        "ai_inbound_messages": [
            {"id": 1, "workspace_id": "ws-a", "conversation_id": "thread-a", "sender_key": "same"},
            {"id": 2, "workspace_id": "ws-a", "conversation_id": "thread-b", "sender_key": "same"},
            {"id": 3, "workspace_id": "ws-b", "conversation_id": "thread-a", "sender_key": "same"},
        ],
        "ai_agent_responses": [
            {"id": 10, "inbound_id": 1, "workspace_id": "ws-a"},
            {"id": 11, "inbound_id": 2, "workspace_id": "ws-a"},
            {"id": 12, "inbound_id": 1, "workspace_id": "ws-b"},
        ],
    }
    monkeypatch.setattr("app.services.ai_conversas_bridge.supabase", SimpleNamespace(table=lambda name: Query(rows[name])))
    inbound, replies = AiConversasBridge()._load_thread_rows({"id": "conversation", "workspace_id": "ws-a", "external_thread_id": "thread-a", "contact_phone": "same"})
    assert [r["id"] for r in inbound] == [1]
    assert [r["id"] for r in replies] == [10]


def test_inbox_listing_filters_workspace_before_pagination(monkeypatch):
    rows = [{"id": 1, "workspace_id": "ws-a"}, {"id": 2, "workspace_id": "ws-b"}]
    monkeypatch.setattr("app.services.ai_conversas_bridge.supabase", SimpleNamespace(table=lambda _name: Query(rows)))
    found = AiConversasBridge()._list_ai_pages("ai_inbound_messages", workspace_id="ws-a")
    assert [r["id"] for r in found] == [1]


def test_opening_conversation_does_not_change_its_external_identity():
    bridge = AiConversasBridge()
    bridge.conversas = MagicMock()
    bridge.mensagens = MagicMock()
    bridge.mensagens.listar_external_ids.return_value = set()
    bridge._load_thread_rows = MagicMock(return_value=([
        {"id": 1, "conversation_id": "other-thread", "text": "mensagem", "created_at": "2026-09-15T00:00:00Z"}
    ], []))
    bridge._upsert_inbound = MagicMock(return_value=True)
    bridge.sync_messages_for_conversa({"id": "conversation", "workspace_id": "ws-a", "external_thread_id": "thread-a"}, "ws-a")
    assert "external_thread_id" not in bridge.conversas.atualizar.call_args.args[1]


def test_missing_workspace_never_expands_contact_history():
    assert AiConversasBridge()._load_thread_rows({"external_thread_id": "thread-a"}) == ([], [])


def test_long_session_history_is_not_truncated_at_one_thousand_messages(monkeypatch):
    rows = [{"id": n, "workspace_id": "ws-a", "conversation_id": "thread-a"} for n in range(1205)]
    monkeypatch.setattr("app.services.ai_conversas_bridge.supabase", SimpleNamespace(table=lambda _name: Query(rows)))
    bridge = AiConversasBridge()
    bridge._query_ai_in = MagicMock(return_value=[])
    inbound, _ = bridge._load_thread_rows({"workspace_id": "ws-a", "external_thread_id": "thread-a"})
    assert len(inbound) == 1205
    assert [row["id"] for row in inbound] == list(range(1205))


def test_scoped_query_failure_does_not_retry_without_scope(monkeypatch):
    bridge = AiConversasBridge()
    bridge._query_ai = MagicMock(side_effect=AssertionError("unscoped fallback"))
    monkeypatch.setattr("app.services.ai_conversas_bridge.supabase", SimpleNamespace(table=MagicMock(side_effect=RuntimeError("unavailable"))))
    assert bridge._query_ai_in("ai_agent_responses", "inbound_id", ["1"], workspace_id="ws-a") == []
    bridge._query_ai.assert_not_called()


def test_same_external_identity_on_different_channels_stays_separate():
    from app.services.ai_conversas_bridge import _ConversaIndex
    rows = [
        {"id": "wa", "channel": "whatsapp", "external_thread_id": "same"},
        {"id": "ig", "channel": "instagram", "external_thread_id": "same"},
    ]
    index = _ConversaIndex(rows)
    assert index.find("same", channel="whatsapp")["id"] == "wa"
    assert index.find("same", channel="instagram")["id"] == "ig"
    groups = AiConversasBridge()._group_threads([
        {"id": 1, "channel": "whatsapp", "conversation_id": "same"},
        {"id": 2, "channel": "instagram", "conversation_id": "same"},
    ], [{"id": 3, "inbound_id": 2, "channel": "instagram"}])
    assert len(groups) == 2
    assert not groups[("whatsapp", "same")]["responses"]
    assert groups[("instagram", "same")]["responses"][0]["id"] == 3


def test_workspace_write_error_never_retries_without_workspace():
    bridge = AiConversasBridge()
    bridge.mensagens = MagicMock()
    bridge.mensagens.obter_por_external_id.return_value = None
    bridge.mensagens.criar.side_effect = RuntimeError("workspace_id foreign key violation")
    assert not bridge._persist_message("conversation", "ai-in-1", {"content": "test"}, "ws-a")
    bridge.mensagens.criar.assert_called_once()
    assert bridge.mensagens.criar.call_args.args[0]["workspace_id"] == "ws-a"
