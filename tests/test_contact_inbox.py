from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from app.repositories.contact_inbox_repository import ContactInboxRepository
from app.services.contact_inbox_service import ContactInboxService, map_contact


def group():
    return {"id": "old", "active_session_id": "new", "workspace_id": "ws",
            "session_ids": ["old", "new"], "last_message": "latest", "last_message_at": "2026-09-15T12:00:00Z",
            "unread_count": 3, "current_session": {"id": "new", "customer_name": "Ana", "status": "waiting"}}


def service():
    svc = ContactInboxService()
    svc.repo = MagicMock()
    svc.sessions = MagicMock()
    svc.sessions._users_index.return_value = {}
    svc.repo.obter.return_value = group()
    return svc


def test_contact_maps_stable_id_and_operational_session_separately():
    result = map_contact(group())
    assert result["id"] == "old"
    assert result["activeSessionId"] == "new"
    assert result["sessionIds"] == ["old", "new"]
    assert result["lastMessage"] == "latest" and result["unreadCount"] == 3


def test_missing_workspace_or_foreign_contact_is_never_expanded():
    svc = service()
    with pytest.raises(HTTPException) as error:
        svc.obter("old", "")
    assert error.value.status_code == 403
    svc.repo.obter.assert_not_called()
    svc.repo.obter.return_value = None
    svc.sessions.conversas.obter.return_value = None
    with pytest.raises(HTTPException) as error:
        svc.obter("foreign", "ws")
    assert error.value.status_code == 404


def test_claim_updates_all_open_sessions_once_and_pauses_each_agent_identity():
    svc = service()
    svc.sessions._usuario_ativo.return_value = {"id": "user", "role": "admin", "name": "User"}
    svc.repo.atualizar_abertas.return_value = [{"id": "old"}, {"id": "new"}]
    with patch('app.services.human_takeover_bridge.mark_human_active') as pause, patch('app.services.contact_inbox_service.invalidate_conversa'):
        result = svc.atuar("old", "ws", "assumir", actor_name="User", assignee_id="user")
    patch_data = svc.repo.atualizar_abertas.call_args.args[2]
    assert patch_data['assigned_to'] == 'user' and patch_data['bot_activated'] is False
    svc.repo.atualizar_abertas.assert_called_once()
    assert pause.call_count == 2
    svc.sessions._registrar_evento.assert_called_once()
    assert svc.sessions._registrar_evento.call_args.args[0] == 'new'
    assert result['id'] == 'old'


def test_closing_all_open_sessions_does_not_rewrite_or_delete_history():
    svc = service()
    svc.repo.atualizar_abertas.return_value = [{"id": "new"}]
    with patch('app.services.contact_inbox_service.invalidate_conversa'):
        svc.atuar('old', 'ws', 'encerrar', actor_name='User')
    patch_data = svc.repo.atualizar_abertas.call_args.args[2]
    assert set(patch_data) == {'status', 'updated_at'}
    assert patch_data['status'] == 'closed'
    svc.repo.mensagens.assert_not_called()


def test_messages_sync_each_exact_session_then_read_one_global_page():
    svc = service()
    sessions = [{"id": "old", "external_thread_id": "provider-a", "workspace_id": "ws"},
                {"id": "new", "external_thread_id": "provider-b", "workspace_id": "ws"}]
    svc.repo.sessoes.return_value = sessions
    svc.repo.mensagens.return_value = [{"id": "msg-old", "conversa_id": "old", "content": "older"},
                                     {"id": "msg-new", "conversa_id": "new", "content": "newer"}]
    with patch('app.services.ai_conversas_bridge.ai_conversas_bridge') as bridge, patch('app.services.inbox_cache.sync_throttle') as throttle, patch('app.services.contact_inbox_service.invalidate_conversa'):
        throttle.should_run.return_value = True
        result = svc.mensagens('old', 'ws', limit=60, before='2026-09-15T13:00:00Z')
    assert [call.args[0] for call in bridge.sync_messages_for_conversa.call_args_list] == sessions
    assert [m['conversationId'] for m in result] == ['old', 'new']
    assert svc.repo.mensagens.call_args.kwargs['limit'] == 60


def test_repository_filters_workspace_and_groups_before_limit():
    query = MagicMock()
    for method in ('select', 'eq', 'contains', 'order', 'limit'):
        getattr(query, method).return_value = query
    query.execute.return_value = SimpleNamespace(data=[group()])
    with patch('app.repositories.contact_inbox_repository.supabase') as db:
        db.table.return_value = query
        repo = ContactInboxRepository()
        assert repo.listar('ws', limit=60) == [group()]
        assert repo.obter('old', 'ws') == group()
    db.table.assert_called_with('conversation_contact_inbox')
    query.eq.assert_called_with('workspace_id', 'ws')
    query.contains.assert_called_once_with('session_ids', ['old'])


def test_unread_requires_assumption_and_reads_only_sessions_owned_by_operator():
    svc = service()
    with pytest.raises(HTTPException) as error:
        svc.marcar_lida('old', 'ws', 'user')
    assert error.value.status_code == 403
    owned = group()
    owned['current_session']['assigned_to'] = 'user'
    svc.repo.obter.return_value = owned
    svc.repo.sessoes.return_value = [{'id': 'new', 'assigned_to': 'user', 'status': 'active'},
                                   {'id': 'old', 'assigned_to': 'user', 'status': 'closed'},
                                   {'id': 'foreign', 'assigned_to': 'another', 'status': 'active'}]
    svc.sessions.marcar_lida.return_value = ({}, None)
    svc.marcar_lida('old', 'ws', 'user')
    svc.sessions.marcar_lida.assert_called_once_with('new', 'user', 'ws')


def test_message_cursor_includes_id_for_equal_timestamps_and_scopes_legacy_rows():
    query = MagicMock()
    for method in ('select', 'or_', 'in_', 'order', 'limit'):
        getattr(query, method).return_value = query
    query.execute.return_value = SimpleNamespace(data=[])
    with patch('app.repositories.contact_inbox_repository.supabase') as db:
        db.table.return_value = query
        ContactInboxRepository().mensagens(group(), 'ws', limit=60,
            before='2026-09-15T13:00:00Z', before_id='00000000-0000-0000-0000-000000000005')
    query.in_.assert_called_once_with('conversa_id', ['old', 'new'])
    assert query.or_.call_count == 2
    assert 'workspace_id.eq.ws,workspace_id.is.null' == query.or_.call_args_list[0].args[0]
    assert 'id.lt.00000000-0000-0000-0000-000000000005' in query.or_.call_args_list[1].args[0]


def test_contact_routes_use_current_session_for_outbound_and_keep_legacy_default():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.routes import conversas as routes
    from app.core.auth import obter_token_payload
    from app.core.workspace_scope import obter_company_context
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[obter_token_payload] = lambda: {'sub': 'user'}
    app.dependency_overrides[obter_company_context] = lambda: {'workspaceId': 'ws'}
    with patch.object(routes, 'contact_inbox') as contacts, patch.object(routes, 'conversas_service') as sessions, patch.object(routes, '_actor_name', return_value='User'):
        contacts.obter.return_value = group()
        contacts.listar.return_value = [map_contact(group())]
        contacts.mensagens.return_value = []
        contacts.atuar.return_value = map_contact(group())
        sessions.enviar_mensagem.return_value = {'id': 'message'}
        sessions.listar_conversas.return_value = []
        client = TestClient(app)
        assert client.get('/conversas?scope=contact').json()[0]['sessionIds'] == ['old', 'new']
        assert client.get('/conversas').json() == []
        sessions.listar_conversas.assert_called_once()
        assert client.post('/conversas/old/mensagens?scope=contact', json={'content': 'Reply'}).status_code == 200
        assert sessions.enviar_mensagem.call_args.args[0] == 'new'
        assert sessions.enviar_mensagem.call_args.kwargs['actor_user_id'] == 'user'
        assert client.patch('/conversas/old/assumir?scope=contact').status_code == 200
        assert contacts.atuar.call_args.args == ('old', 'ws', 'assumir')
        assert client.get('/conversas/old/mensagens?scope=contact&beforeId=invalid').status_code == 422
