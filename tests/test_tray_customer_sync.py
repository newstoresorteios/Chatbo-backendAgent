from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from app.services import tray_customer_sync as module


def test_identity_and_sparse_contacts():
    payload = module.customer_payload({"Customer": {"id": "12", "name": "Ana",
        "cellphone": "(21) 99999-1234", "email": ""}}, "company-a")
    assert payload == {"workspace_id": "company-a", "tray_id": "12",
                       "nome": "Ana", "celular": "(21) 99999-1234"}
    assert "mercos_id" not in payload
    with pytest.raises(ValueError):
        module.customer_payload({"name": "Missing ID"}, "company-a")


def test_pages_use_company_integration_and_stable_upsert(monkeypatch):
    client = Mock()
    client.list_customers.return_value = [{"id": "1", "name": "Ana"}]
    client.customer_detail.return_value = {"id": "1", "cellphone": "21999991234"}
    integrations = Mock()
    integrations.get_configured.return_value = {"provider": "tray"}
    integrations.client_from_workspace.return_value = client
    monkeypatch.setattr(module, "workspace_integration_service", integrations)
    query = Mock()
    query.upsert.return_value = query
    monkeypatch.setattr(module, "supabase", SimpleNamespace(table=lambda _: query))
    sync = module.TrayCustomerSync()
    assert sync.sync_page("company-a", page=3, limit=1)["nextPage"] == 4
    client.list_customers.assert_called_once_with(page=3, limit=1)
    query.upsert.assert_called_once_with(
        [{"workspace_id": "company-a", "tray_id": "1", "nome": "Ana", "celular": "21999991234",
          "tray_contacts_pending": False, "tray_modified_at": ""}],
        on_conflict="workspace_id,tray_id")
    client.list_customers.return_value = []
    assert sync.sync_page("company-a", page=4)["nextPage"] is None
    integrations.get_configured.return_value = {"provider": "mercos"}
    with pytest.raises(ValueError):
        sync.sync_page("company-b")


def test_wrong_detail_never_writes_customer(monkeypatch):
    client = Mock()
    client.list_customers.return_value = [{"id": "1"}]
    client.customer_detail.return_value = {"id": "2"}
    integrations = Mock()
    integrations.get_configured.return_value = {"provider": "tray"}
    integrations.client_from_workspace.return_value = client
    monkeypatch.setattr(module, "workspace_integration_service", integrations)
    db = Mock()
    monkeypatch.setattr(module, "supabase", db)
    with pytest.raises(ValueError):
        module.TrayCustomerSync().sync_page("company-a")
    db.table.assert_not_called()
