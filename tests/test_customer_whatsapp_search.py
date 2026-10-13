from types import SimpleNamespace
from unittest.mock import Mock

from app.services import pulsedesk_adapter as adapter


def test_whatsapp_filter_before_pagination_and_company_scope(monkeypatch):
    rows = [
        {"id": "1", "nome": "Sem número"},
        {"id": "2", "nome": "Ana", "celular": "(11) 99999-1234", "telefone": "123"},
        {"id": "3", "nome": "Bruno", "telefone": "(21) 98888-1234"},
    ]
    query = Mock()
    query.select.return_value = query
    query.execute.return_value = SimpleNamespace(data=rows)
    monkeypatch.setattr(adapter, 'supabase', SimpleNamespace(table=lambda _: query))
    scope = Mock(return_value=query)
    monkeypatch.setattr(adapter, 'apply_workspace_filter', scope)

    result = adapter.listar_clientes(page_size=1, workspace_id='company-a', whatsapp_only=True)
    scope.assert_called_once_with(query, 'company-a')
    assert result['total'] == 2
    assert result['totalPages'] == 2
    assert result['data'][0]['phone'] == '5511999991234'

    result = adapter.listar_clientes(search='(21) 98888', workspace_id='company-a', whatsapp_only=True)
    assert [customer['name'] for customer in result['data']] == ['Bruno']
    assert rows[1]['telefone'] == '123'
