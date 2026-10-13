from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from fastapi import HTTPException
from app.services import customer_conversation_service as module

CUSTOMER_ID = '11111111-1111-1111-1111-111111111111'


def setup(monkeypatch, rows):
    query = Mock()
    for method in ('select', 'eq', 'limit'):
        getattr(query, method).return_value = query
    query.execute.return_value = SimpleNamespace(data=rows)
    monkeypatch.setattr(module, 'supabase', SimpleNamespace(table=lambda _: query))
    repo = Mock()
    repo.obter_por_contato.return_value = None
    repo.criar.return_value = {'id': 'new-session'}
    monkeypatch.setattr(module, 'ConversaRepository', lambda: repo)
    inbox = Mock()
    inbox.obter.return_value = {'contact': True}
    monkeypatch.setattr(module, 'ContactInboxService', lambda: inbox)
    monkeypatch.setattr(module, 'map_contact', lambda group, _: group)
    monkeypatch.setattr(module, 'invalidate_conversa', Mock())
    return query, repo


def test_new_contact_uses_stored_phone_company_and_actor_without_sending(monkeypatch):
    query, repo = setup(monkeypatch, [{'id': CUSTOMER_ID, 'nome': 'Ana', 'celular': '(21) 99999-1234'}])
    assert module.CustomerConversationService().open(CUSTOMER_ID, 'company-a', 'actor-a') == {'contact': True}
    assert ('workspace_id', 'company-a') in [call.args for call in query.eq.call_args_list]
    payload = repo.criar.call_args.args[0]
    assert payload['contact_phone'] == '5521999991234'
    assert payload['cliente_id'] == CUSTOMER_ID
    assert payload['assigned_to'] == 'actor-a'
    assert payload['bot_activated'] is False
    assert repo.criar.call_args.kwargs == {'workspace_id': 'company-a'}


def test_existing_contact_is_reused_without_reassigning(monkeypatch):
    _, repo = setup(monkeypatch, [{'id': CUSTOMER_ID, 'celular': '21999991234'}])
    repo.obter_por_contato.return_value = {'id': 'existing', 'assigned_to': 'other-user'}
    module.CustomerConversationService().open(CUSTOMER_ID, 'company-a', 'actor-a')
    repo.criar.assert_not_called()
    repo.atualizar.assert_not_called()


def test_customer_from_another_company_is_rejected(monkeypatch):
    _, repo = setup(monkeypatch, [])
    with pytest.raises(HTTPException) as error:
        module.CustomerConversationService().open(CUSTOMER_ID, 'company-a', 'actor-a')
    assert error.value.status_code == 404
    repo.criar.assert_not_called()


def test_invalid_phone_cannot_start_contact(monkeypatch):
    _, repo = setup(monkeypatch, [{'id': CUSTOMER_ID, 'telefone': '123'}])
    with pytest.raises(HTTPException) as error:
        module.CustomerConversationService().open(CUSTOMER_ID, 'company-a', 'actor-a')
    assert error.value.status_code == 400
    repo.criar.assert_not_called()
