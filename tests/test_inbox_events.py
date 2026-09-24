import asyncio
from unittest.mock import MagicMock, patch

from app.services.inbox_events import InboxEvents
from app.services.inbox_events import is_new_customer_message
from datetime import datetime, timezone, timedelta
from app.services.ai_conversas_bridge import AiConversasBridge


def test_events_isolate_workspaces_and_timeout_without_data():
    async def check():
        hub = InboxEvents()
        cursor = hub.cursor('a')
        await hub.publish('b')
        result = await hub.wait('a', cursor, timeout=0.001)
        assert result == {'cursor': cursor, 'changed': False, 'realtime': False,
                          'incoming': {'cursor': f'{hub.boot}:0', 'at': 0}}
        await hub.publish('a')
        assert (await hub.wait('a', cursor))['changed'] is True
        assert (await hub.wait('b', ''))['cursor'] != hub.cursor('a')
    asyncio.run(check())


def test_sound_signal_only_for_customer_inserts_not_history_or_duplicates():
    hub = InboxEvents()
    row = {'id': 1, 'created_at': datetime.now(timezone.utc).isoformat()}
    assert is_new_customer_message('ai_inbound_messages', row, 'INSERT')
    assert not is_new_customer_message('ai_inbound_messages', row, 'UPDATE')
    assert not is_new_customer_message('ai_agent_responses', row, 'INSERT')
    assert not is_new_customer_message('mensagens', {'sender': 'ai'}, 'INSERT')
    assert not is_new_customer_message('mensagens', {'sender': 'customer', 'external_id': 'ai-in-1'}, 'INSERT')
    assert is_new_customer_message('mensagens', {'sender': 'customer'}, 'INSERT')
    hub.mark_incoming('a', 'ai_inbound_messages', row, 'INSERT')
    first = hub.incoming['a'].copy()
    hub.mark_incoming('a', 'ai_inbound_messages', row, 'INSERT')
    assert hub.incoming['a'] == first
    assert 'b' not in hub.incoming
    old = {'id': 2, 'created_at': (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()}
    hub.mark_incoming('a', 'ai_inbound_messages', old, 'INSERT')
    hub.mark_incoming('a', 'ai_inbound_messages', {'id': 3, 'created_at': 'invalid'}, 'INSERT')
    assert hub.incoming['a'] == first


def test_pending_wait_wakes_on_change_and_restarts_resync():
    async def check():
        hub = InboxEvents()
        pending = asyncio.create_task(hub.wait('a', hub.cursor('a')))
        await asyncio.sleep(0)
        await hub.publish('a')
        assert (await pending)['changed']
        assert (await InboxEvents().wait('a', hub.cursor('a')))['changed']
    asyncio.run(check())


def test_null_workspace_unknown_table_and_delete_are_ignored():
    hub = InboxEvents()
    for payload in [ {}, {'data': {'table': 'mensagens', 'record': {}}},
                     {'data': {'table': 'unknown', 'record': {'workspace_id': 'a'}}},
                     {'data': {'table': 'mensagens', 'old_record': {'workspace_id': 'a'}}} ]:
        hub.receive(payload)
    assert hub.queue.empty()
    hub.receive({'data': {'table': 'mensagens', 'record': {'workspace_id': 'a'}}})
    assert hub.queue.get_nowait()[1]['workspace_id'] == 'a'


def test_consumer_syncs_before_notifying_and_invalidates_caches():
    async def check():
        hub = InboxEvents()
        hub.receive({'data': {'table': 'ai_inbound_messages', 'record': {'workspace_id': 'a'}}})
        with patch('app.services.ai_conversas_bridge.ai_conversas_bridge.sync_event') as sync:
            task = asyncio.create_task(hub.consume())
            await hub.queue.join()
            sync.assert_called_once()
            assert hub.cursor('a') != f'{hub.boot}:0'
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    asyncio.run(check())


def test_response_event_resolves_inbound_in_same_workspace():
    bridge = AiConversasBridge()
    bridge._query_ai_in = MagicMock(return_value=[{'id': 1, 'workspace_id': 'a', 'conversation_id': 'ig:1'}])
    bridge._ensure_conversa = MagicMock(return_value={'id': 'c', 'workspace_id': 'a'})
    bridge.sync_messages_for_conversa = MagicMock()
    bridge.sync_event('ai_agent_responses', {'workspace_id': 'a', 'inbound_id': 1})
    assert bridge._query_ai_in.call_args.kwargs['workspace_id'] == 'a'
    bridge.sync_messages_for_conversa.assert_called_once_with({'id': 'c', 'workspace_id': 'a'}, 'a')
    bridge._query_ai_in.return_value = [{'workspace_id': 'b', 'conversation_id': 'foreign'}]
    bridge.sync_event('ai_agent_responses', {'workspace_id': 'a', 'inbound_id': 2})
    assert bridge._ensure_conversa.call_count == 1


def test_event_route_requires_auth_and_uses_server_workspace():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from unittest.mock import AsyncMock
    from app.routes.conversas import router
    from app.core.workspace_scope import obter_company_context
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    assert client.get('/conversas/events').status_code in (401, 403)
    app.dependency_overrides[obter_company_context] = lambda: {'workspaceId': 'server-workspace'}
    with patch('app.services.inbox_events.inbox_events') as hub:
        hub.wait = AsyncMock(return_value={'cursor': 'next', 'changed': True, 'realtime': True})
        response = client.get('/conversas/events?workspaceId=foreign&cursor=old')
        assert response.status_code == 200
        assert response.headers['cache-control'] == 'no-store'
        hub.wait.assert_awaited_once_with('server-workspace', 'old')
        assert client.get('/conversas/events?cursor=' + 'a' * 101).status_code == 422


def test_contact_list_cache_does_not_treat_api_rows_as_database_groups():
    from app.services.contact_inbox_service import ContactInboxService
    from app.services.inbox_cache import conversas_cache
    key = 'conversas:cache-test:contacts:60:latest'
    rows = [{'id': 'c', 'sessionIds': ['c'], 'activeSessionId': 'c'}]
    conversas_cache.set(key, rows, 2)
    try:
        with patch('app.services.conversas_service._kick_workspace_sync'):
            assert ContactInboxService().listar('cache-test') == rows
    finally:
        conversas_cache.delete(key)
