from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException
from app.services.commercial_leads import intent_stage, project_lead, list_commercial_leads


def group():
    return {'id': 'contact', 'active_session_id': 'session', 'session_ids': ['session'],
            'last_message_at': datetime.now(timezone.utc).isoformat(), 'current_session': {'id': 'session', 'customer_name': 'Thi', 'channel': 'instagram'}}


def message(text, sender='customer', index=1):
    return {'id': str(index), 'content': text, 'sender': sender, 'created_at': datetime.now(timezone.utc).isoformat()}


@pytest.mark.parametrize('text,stage', [
    ('Vocês teriam o Tissot heritage 1938 na cor salmão a pronta entrega?', 'high_intent'),
    ('Despachou amigão?', 'post_sale'), ('Meu pedido 26116', 'post_sale'),
    ('Qual valor?', 'interest'), ('Obrigado!', None), ('Quero comprar', 'high_intent'),
    ('Não quero comprar', 'lost'),
    ('Quero comprar esse relógio. Qual a garantia?', 'high_intent'),
    ('Quero comprar. Qual a política de troca?', 'high_intent'),
    ('Quero comprar esse relógio. Tem assistência?', 'high_intent'),
    ('Qual a garantia e a política de troca?', 'interest'),
    ('Quero acionar a garantia do meu relógio', 'post_sale'),
    ('Já comprei e preciso de assistência', 'post_sale'),
])
def test_intent(text, stage):
    assert intent_stage(text) == stage


def test_bot_cannot_create_hot_lead_and_history_is_distinct():
    result = project_lead(group(), [message('Pode comprar à pronta entrega', 'ai')])
    assert result['score'] == 30
    result = project_lead(group(), [message('quero comprar'), message('quanto?', index=2), message('meu pedido já chegou?', index=3)])
    assert result['stage'] == 'post_sale'
    assert result['score'] < 50
    assert 'high_intent' in result['observedStages']


def test_commercial_route_refreshes_without_cache_and_keeps_workspace_scope():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.routes.conversas import router
    from app.core.workspace_scope import obter_company_context
    api = FastAPI()
    api.include_router(router)
    api.dependency_overrides[obter_company_context] = lambda: {'company_id': 'workspace'}
    with patch('app.routes.conversas.workspace_id_from_context', return_value='workspace'), patch('app.services.commercial_leads.list_commercial_leads', return_value={'items': []}) as load:
        response = TestClient(api).get('/commercial/leads?page=2&page_size=25')
    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'
    load.assert_called_once_with('workspace', 2, 25)


def test_high_intent_survives_price_followup_and_closed_is_not_sale():
    result = project_lead(group(), [message('quero comprar'), message('qual valor?', index=2)])
    assert result['score'] == 90
    g = group()
    g['current_session']['status'] = 'closed'
    result = project_lead(g, [message('quero comprar')])
    assert result['stage'] == 'closed'


def test_workspace_required_before_query():
    with patch('app.services.commercial_leads.supabase') as db:
        with pytest.raises(HTTPException):
            list_commercial_leads('')
        db.table.assert_not_called()


@pytest.mark.parametrize('hours,stage,label', [(23.99, 'high_intent', 'Quente'), (24, 'follow_up', 'Morno'), (167, 'follow_up', 'Morno'), (168, 'follow_up', 'Frio'), (240, 'follow_up', 'Frio')])
def test_hot_lead_expires_after_one_day(hours, stage, label):
    now = datetime.now(timezone.utc)
    msg = message('Quero comprar à pronta entrega')
    msg['created_at'] = (now - timedelta(hours=hours)).isoformat()
    # A fresh assistant answer/last interaction must not reheat an old lead.
    result = project_lead(group(), [msg, message('Vamos fechar?', sender='ai')], now=now)
    assert (result['stage'], result['label']) == (stage, label)
    assert 'high_intent' in result['observedStages']


@pytest.mark.parametrize('hours', [24, 168, 192])
def test_recent_price_question_renews_expired_interest(hours):
    now = datetime.now(timezone.utc)
    old = message('Quero comprar')
    old['created_at'] = (now - timedelta(hours=hours)).isoformat()
    fresh = message('Qual o valor atualizado?', index=2)
    fresh['created_at'] = now.isoformat()
    result = project_lead(group(), [old, fresh], now=now)
    assert (result['stage'], result['score']) == ('interest', 65)
    assert result['evidence'] == fresh['content']
    assert result['intentAgeHours'] == 0
    assert 'high_intent' in result['observedStages']


def test_price_followup_does_not_extend_hot_purchase_deadline():
    now = datetime.now(timezone.utc)
    old = message('Quero comprar')
    old['created_at'] = (now - timedelta(hours=25)).isoformat()
    followup = message('Qual o valor?', index=2)
    followup['created_at'] = (now - timedelta(hours=2)).isoformat()
    assert project_lead(group(), [old, followup], now=now)['stage'] == 'follow_up'


def test_empty_workspace_page_scoped_and_paginated():
    db = MagicMock()
    query = db.table.return_value
    for method in ('select', 'eq', 'order', 'range'):
        getattr(query, method).return_value = query
    query.execute.return_value.data = []
    query.execute.return_value.count = 0
    with patch('app.services.commercial_leads.supabase', db), patch('app.services.conversas_service.ConversasService._users_index', return_value={}):
        result = list_commercial_leads('workspace', 2, 100)
    query.eq.assert_called_with('workspace_id', 'workspace')
    query.range.assert_called_once_with(100, 199)
    assert result['items'] == [] and not result['hasMore']


def test_unopened_meta_conversation_uses_original_inbound():
    from types import SimpleNamespace
    class Query:
        def __init__(self, table):
            self.table = table
            self.filters = []
        def __getattr__(self, name):
            def chain(*args, **kwargs):
                self.filters.append((name, args))
                return self
            return chain
        def execute(self):
            if self.table in {'conversas', 'ai_inbound_messages', 'conversation_contact_inbox'}:
                assert ('eq', ('workspace_id', 'workspace')) in self.filters
            rows = {
                'conversation_contact_inbox': [group()],
                'conversas': [{'id': 'session', 'external_thread_id': 'ig:123', 'channel': 'instagram'}],
                'mensagens': [],
                'ai_inbound_messages': [{'id': 1, 'conversation_id': 'ig:123', 'channel': 'instagram',
                                         'text': 'Tissot pronta entrega?', 'created_at': datetime.now(timezone.utc).isoformat()}],
            }
            return SimpleNamespace(data=rows[self.table], count=1)
    with patch('app.services.commercial_leads.supabase') as db, patch('app.services.conversas_service.ConversasService._users_index', return_value={}):
        db.table.side_effect = Query
        result = list_commercial_leads('workspace')
    assert result['items'][0]['score'] == 90
    assert result['historyComplete']
