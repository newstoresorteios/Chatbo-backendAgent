from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.services import conversation_agent_context_service as module


class MemoryDatabase:
    """Offline PostgREST double applying the actual query filters to shared rows."""

    def __init__(self, rows=None, *, ignore_filters=False, fail=False):
        self.rows = rows or {}
        self.queries = []
        self.ignore_filters = ignore_filters
        self.fail = fail

    def table(self, table):
        db = self

        class Query:
            def __init__(self):
                self.filters = []
                self.maximum = None

            def select(self, _):
                return self

            def eq(self, column, value):
                self.filters.append((column, value))
                return self

            def order(self, *_, **__):
                return self

            def limit(self, value):
                self.maximum = value
                return self

            def execute(self):
                db.queries.append((table, self.filters))
                if db.fail:
                    raise RuntimeError("legacy schema without workspace_id; sensitive sender")
                rows = db.rows.get(table, [])
                if not db.ignore_filters:
                    rows = [row for row in rows if all(row.get(k) == v for k, v in self.filters)]
                return SimpleNamespace(data=rows[:self.maximum])

        return Query()


@pytest.fixture
def service(monkeypatch):
    instance = module.ConversationAgentContextService()
    instance.conversas = MagicMock()
    instance.conversas.obter.return_value = {
        "id": "conversation", "workspace_id": "allowed", "contact_phone": "shared-sender",
        "external_thread_id": "shared-thread",
    }
    monkeypatch.setattr(module.workspace_service, "get_current_workspace_context",
                        MagicMock(return_value={"workspaceId": "allowed"}))
    monkeypatch.setattr(module, "supabase", MemoryDatabase())
    return instance


@pytest.mark.parametrize("workspace", [None, "", "   "])
def test_missing_workspace_fails_before_any_read(service, workspace):
    with pytest.raises(HTTPException) as caught:
        service.obter("conversation", {"id": "operator"}, workspace)
    assert caught.value.status_code == 403
    service.conversas.obter.assert_not_called()
    module.workspace_service.get_current_workspace_context.assert_not_called()
    assert not module.supabase.queries


def test_foreign_workspace_cannot_be_selected_by_caller(service):
    with pytest.raises(HTTPException) as caught:
        service.obter("conversation", {"id": "operator", "workspace_id": "foreign"}, "foreign")
    assert caught.value.status_code == 403
    module.workspace_service.get_current_workspace_context.assert_called_once_with(
        {"id": "operator", "workspace_id": "foreign"})
    service.conversas.obter.assert_not_called()
    assert not module.supabase.queries


def test_missing_authenticated_user_cannot_read_context(service):
    with pytest.raises(HTTPException) as caught:
        service.obter("conversation", {}, "allowed")
    assert caught.value.status_code == 401
    service.conversas.obter.assert_not_called()
    assert not module.supabase.queries


@pytest.mark.parametrize("conversation", [None, {"workspace_id": "foreign"}, {"workspace_id": None}, {}])
def test_no_unscoped_fallback_for_missing_or_foreign_conversation(service, conversation):
    service.conversas.obter.return_value = conversation
    with pytest.raises(HTTPException) as caught:
        service.obter("conversation", {"id": "operator"}, "allowed")
    assert caught.value.status_code == 404
    service.conversas.obter.assert_called_once_with("conversation", workspace_id="allowed")
    assert not module.supabase.queries


def test_same_sender_in_two_workspaces_never_shares_context(service, monkeypatch):
    tables = ("ai_remarketing_contacts", "ai_conversation_statuses", "ai_contact_memories",
              "ai_agent_responses", "ai_pix_payments")
    rows = {table: [
        {"id": f"{scope}-{table}", "workspace_id": scope, "sender_key": "shared-sender",
         "contact_id": "allowed-ai_remarketing_contacts", "scope_status": "verified",
         "status": "active", "safe_summary": scope, "reply_text": scope, "qr_code": scope}
        for scope in ("foreign", None, "allowed")
    ] for table in tables}
    rows["ai_contact_memories"].insert(0, {
        "id": "quarantined", "workspace_id": "allowed", "sender_key": "shared-sender",
        "status": "active", "scope_status": "quarantined", "safe_summary": "do not expose",
    })
    rows["ai_contact_memories"].insert(0, {
        "id": "unverified", "workspace_id": "allowed", "sender_key": "shared-sender",
        "status": "active", "safe_summary": "do not expose",
    })
    db = MemoryDatabase(rows)
    monkeypatch.setattr(module, "supabase", db)
    result = service.obter("conversation", {"id": "operator"}, "allowed")
    assert result["conversationId"] == "conversation"
    for key in ("contact", "status"):
        assert result[key]["id"].startswith("allowed-")
    for key in ("memories", "recentResponses", "pixPayments"):
        assert len(result[key]) == 1
        assert result[key][0]["id"].startswith("allowed-")
    assert {table for table, _ in db.queries} == set(tables)
    for table, filters in db.queries:
        assert ("workspace_id", "allowed") in filters
        if table == "ai_contact_memories":
            assert ("scope_status", "verified") in filters


def test_pix_fallback_by_conversation_is_scoped_too(service, monkeypatch):
    db = MemoryDatabase({"ai_pix_payments": [
        {"id": scope, "workspace_id": scope, "conversation_id": "shared-thread", "qr_code": scope}
        for scope in ("foreign", None, "allowed")
    ]})
    monkeypatch.setattr(module, "supabase", db)
    result = service.obter("conversation", {"id": "operator"}, "allowed")
    assert [row["id"] for row in result["pixPayments"]] == ["allowed"]
    fallback = [filters for table, filters in db.queries
                if table == "ai_pix_payments" and ("conversation_id", "shared-thread") in filters]
    assert fallback and all(("workspace_id", "allowed") in filters for filters in fallback)


@pytest.mark.parametrize("table", ["ai_contact_memories", "ai_agent_responses", "ai_pix_payments",
                                   "ai_remarketing_contacts", "ai_conversation_statuses"])
def test_rejects_foreign_and_legacy_rows_even_if_database_ignores_scope(monkeypatch, table):
    rows = [{"workspace_id": scope, "scope_status": "verified"} for scope in ("foreign", None)]
    if table == "ai_contact_memories":
        rows += [{"workspace_id": "allowed", "scope_status": status} for status in (None, "quarantined")]
    monkeypatch.setattr(module, "supabase", MemoryDatabase({table: rows}, ignore_filters=True))
    assert module._query_ai(table, {}, workspace_id="allowed") == []


def test_legacy_schema_error_does_not_trigger_unscoped_query_or_log_sender(monkeypatch, caplog):
    db = MemoryDatabase(fail=True)
    monkeypatch.setattr(module, "supabase", db)
    assert module._query_ai("ai_contact_memories", {"sender_key": "sensitive sender"},
                            workspace_id="allowed") == []
    assert len(db.queries) == 1
    assert ("workspace_id", "allowed") in db.queries[0][1]
    assert "sensitive sender" not in caplog.text


def test_query_helper_rejects_missing_scope_without_database_call(monkeypatch):
    db = MemoryDatabase()
    monkeypatch.setattr(module, "supabase", db)
    with pytest.raises(HTTPException):
        module._query_ai("ai_pix_payments", {}, workspace_id="")
    assert not db.queries


@pytest.mark.parametrize("scope,path_id,session_id", [
    ("session", "conversation", "conversation"), ("contact", "contact-group", "active-session"),
])
def test_existing_route_contract_passes_authenticated_scope(scope, path_id, session_id, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.routes import conversas as routes

    app = FastAPI()
    app.include_router(routes.router)
    user = {"id": "operator"}
    app.dependency_overrides[routes.obter_usuario_atual] = lambda: user
    app.dependency_overrides[routes.obter_company_context] = lambda: {"workspaceId": "allowed"}
    contacts = MagicMock()
    contacts.obter.return_value = {"active_session_id": session_id}
    reader = MagicMock()
    reader.obter.return_value = {"conversationId": session_id, "memories": [], "pixPayments": []}
    monkeypatch.setattr(routes, "contact_inbox", contacts)
    monkeypatch.setattr(routes, "conversation_agent_context_service", reader)
    response = TestClient(app).get(f"/conversas/{path_id}/agente?scope={scope}")
    assert response.status_code == 200
    assert response.json()["conversationId"] == session_id
    reader.obter.assert_called_once_with(session_id, user, "allowed")
    if scope == "contact":
        contacts.obter.assert_called_once_with(path_id, "allowed")
    else:
        contacts.obter.assert_not_called()
