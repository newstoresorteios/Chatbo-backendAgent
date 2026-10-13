from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import Mock

from app.routes import tray_customers as routes
from app.core.workspace_scope import obter_company_context


def test_sync_requires_authentication():
    app = FastAPI()
    app.include_router(routes.router, prefix="/api")
    assert TestClient(app).post("/api/tray/clientes/sincronizar", json={}).status_code == 403


def test_sync_uses_authenticated_company_and_validates_page(monkeypatch):
    app = FastAPI()
    app.include_router(routes.router, prefix="/api")
    app.dependency_overrides[obter_company_context] = lambda: {"workspaceId": "company-a"}
    permission = next(dep.call for route in routes.router.routes
                      for dep in route.dependant.dependencies
                      if dep.name == "_")
    app.dependency_overrides[permission] = lambda: {"perfil": "admin"}
    sync = Mock(return_value={"synced": 1, "page": 2, "nextPage": None})
    monkeypatch.setattr(routes.tray_customer_sync, "sync_page", sync)
    client = TestClient(app)
    response = client.post("/api/tray/clientes/sincronizar",
                           json={"page": 2, "workspaceId": "company-b"})
    assert response.status_code == 200
    sync.assert_called_once_with("company-a", page=2, limit=50)
    assert client.post("/api/tray/clientes/sincronizar", json={"page": 0}).status_code == 422
