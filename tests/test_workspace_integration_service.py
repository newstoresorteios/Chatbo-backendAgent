from app.services.workspace_integration_service import WorkspaceIntegrationService
from app.services.mercos_adaptor_client import MercosAdaptorClient


class FakeQuery:
    def __init__(self, database, table):
        self.database = database
        self.table = table
        self.filters = []
        self.operation = "select"
        self.payload = None

    def select(self, *_args):
        return self

    def eq(self, key, value):
        self.filters.append((key, value))
        return self

    def update(self, payload):
        self.operation = "update"
        self.payload = payload
        return self

    def insert(self, payload):
        self.operation = "insert"
        self.payload = payload
        return self

    def limit(self, _value):
        return self

    def execute(self):
        rows = self.database.setdefault(self.table, [])
        matches = [
            row for row in rows
            if all(row.get(key) == value for key, value in self.filters)
        ]
        if self.operation == "update":
            for row in matches:
                row.update(self.payload)
            data = matches
        elif self.operation == "insert":
            inserted = {"id": f"row-{len(rows) + 1}", **self.payload}
            rows.append(inserted)
            data = [inserted]
        else:
            data = matches
        return type("Response", (), {"data": data})()


class FakeSupabase:
    def __init__(self, rows):
        self.database = {"workspace_integrations": rows}

    def table(self, name):
        return FakeQuery(self.database, name)


def test_upsert_mercos_disables_tray_and_becomes_configured(monkeypatch):
    rows = [{
        "id": "tray-row",
        "workspace_id": "workspace-1",
        "provider": "tray",
        "status": "connected",
        "configuration": {"adapterBaseUrl": "https://tray.test", "adapterToken": "tray-token"},
        "updated_at": "2026-09-01T00:00:00",
    }]
    fake = FakeSupabase(rows)
    monkeypatch.setattr("app.services.workspace_integration_service.supabase", fake)
    service = WorkspaceIntegrationService()

    saved = service.upsert(
        "workspace-1",
        provider="mercos",
        adapter_base_url="https://mercos-adaptor.test/",
        adapter_token="mercos-token",
    )

    assert saved["provider"] == "mercos"
    assert saved["configuration"]["adapterBaseUrl"] == "https://mercos-adaptor.test"
    assert rows[0]["status"] == "disconnected"
    assert service.get_configured("workspace-1")["provider"] == "mercos"
    assert service.public_view(saved)["hasToken"] is True


def test_upsert_mercos_keeps_existing_token_when_blank(monkeypatch):
    rows = [{
        "id": "mercos-row",
        "workspace_id": "workspace-1",
        "provider": "mercos",
        "status": "connected",
        "configuration": {"adapterBaseUrl": "https://old.test", "adapterToken": "saved-token"},
        "updated_at": "2026-09-01T00:00:00",
    }]
    monkeypatch.setattr(
        "app.services.workspace_integration_service.supabase",
        FakeSupabase(rows),
    )
    service = WorkspaceIntegrationService()

    saved = service.upsert(
        "workspace-1",
        provider="mercos",
        adapter_base_url="https://new.test",
        adapter_token="",
    )

    assert saved["configuration"]["adapterToken"] == "saved-token"


def test_client_from_workspace_selects_mercos_client(monkeypatch):
    rows = [{
        "id": "mercos-row",
        "workspace_id": "workspace-1",
        "provider": "mercos",
        "status": "connected",
        "configuration": {
            "adapterBaseUrl": "https://mercos-adaptor.test",
            "adapterToken": "internal-key",
        },
        "updated_at": "2026-09-01T00:00:00",
    }]
    monkeypatch.setattr(
        "app.services.workspace_integration_service.supabase",
        FakeSupabase(rows),
    )

    client = WorkspaceIntegrationService().client_from_workspace("workspace-1")

    assert isinstance(client, MercosAdaptorClient)
    assert client._headers()["x-api-key"] == "internal-key"
