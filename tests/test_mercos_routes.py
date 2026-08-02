"""Testes das rotas Mercos (/api/mercos/*)."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.auth import obter_token_payload
from app.services.mercos_service import MercosService
from main import app


PEDIDO_VALIDO = {
    "cliente_id": 9282664,
    "data_emissao": "2026-07-09",
    "condicao_pagamento": "a vista",
    "itens": [
        {
            "produto_id": 20386166,
            "quantidade": 1,
            "preco_tabela": 29.9,
        }
    ],
}


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _auth_as(role: str):
    def _payload():
        return {
            "sub": "user-1",
            "email": f"{role}@test.com",
            "role": role,
            "jti": "test-jti",
        }

    app.dependency_overrides[obter_token_payload] = _payload


def test_listar_clientes(client):
    _auth_as("user")
    with patch.object(MercosService, "listar_clientes", return_value=[{"id": 1, "nome": "A"}]):
        resp = client.get("/api/mercos/clientes")
    assert resp.status_code == 200
    assert resp.json()[0]["nome"] == "A"


def test_listar_produtos(client):
    _auth_as("user")
    with patch.object(MercosService, "listar_produtos", return_value=[{"id": 2, "nome": "P"}]):
        resp = client.get("/api/mercos/produtos")
    assert resp.status_code == 200
    assert resp.json()[0]["id"] == 2


def test_listar_pedidos(client):
    _auth_as("user")
    with patch.object(MercosService, "listar_pedidos", return_value=[{"id": 3}]):
        resp = client.get("/api/mercos/pedidos")
    assert resp.status_code == 200
    assert resp.json()[0]["id"] == 3


def test_criar_pedido_payload_valido(client):
    _auth_as("admin")
    with patch.object(
        MercosService,
        "criar_pedido",
        return_value={"status_code": 201, "resposta": {}, "meuspedidosid": "99"},
    ) as mock_criar:
        resp = client.post("/api/mercos/pedidos", json=PEDIDO_VALIDO)
    assert resp.status_code == 200
    assert resp.json()["meuspedidosid"] == "99"
    mock_criar.assert_called_once()
    payload = mock_criar.call_args.args[-1]
    assert payload["cliente_id"] == 9282664
    assert payload["itens"][0]["produto_id"] == 20386166


def test_criar_pedido_payload_invalido_422(client):
    _auth_as("admin")
    resp = client.post("/api/mercos/pedidos", json={"cliente_id": 1})
    assert resp.status_code == 422


def test_erro_400_mercos_vira_http_exception(client):
    _auth_as("admin")
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.json.return_value = {"mensagem": "cliente inválido"}
    mock_resp.text = ""
    mock_resp.headers = {}
    mock_resp.request = MagicMock(method="POST", path_url="/v2/pedidos")

    with patch.object(MercosService, "_request", return_value=mock_resp):
        resp = client.post("/api/mercos/pedidos", json=PEDIDO_VALIDO)

    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["mercos_status"] == 400
    assert detail["resposta"]["mensagem"] == "cliente inválido"


def test_usuario_sem_permissao_nao_cria(client):
    _auth_as("vendedor")
    resp = client.post("/api/mercos/pedidos", json=PEDIDO_VALIDO)
    assert resp.status_code == 403


def test_usuario_manage_integrations_pode_criar(client):
    _auth_as("supervisor")
    with patch.object(
        MercosService,
        "criar_pedido",
        return_value={"status_code": 201, "resposta": {}, "meuspedidosid": "1"},
    ):
        resp = client.post("/api/mercos/pedidos", json=PEDIDO_VALIDO)
    assert resp.status_code == 200


def test_homologacao_continua_funcionando(client):
    _auth_as("admin")
    fake = {
        "prontoParaHomologacao": True,
        "ambiente": {"isSandbox": True},
        "criteriosObrigatorios": {},
        "apisLeitura": {},
        "contagens": {},
        "erros": {},
    }
    with patch.object(MercosService, "status_homologacao", return_value=fake):
        resp = client.get("/api/mercos/homologacao")
    assert resp.status_code == 200
    assert resp.json()["prontoParaHomologacao"] is True


def test_sincronizar_producao_exige_confirm_production(client):
    _auth_as("admin")
    with patch(
        "app.routes.mercos.mercos_info",
        return_value={"isProduction": True, "environment": "production"},
    ):
        resp = client.post(
            "/api/mercos/sincronizar",
            json={"type": "all", "confirmProduction": False},
        )
    assert resp.status_code == 400
    assert "confirmProduction" in str(resp.json()["detail"])


def test_testar_conexao_continua_funcionando(client):
    _auth_as("user")
    with patch.object(MercosService, "listar_clientes", return_value=[{"id": 1}, {"id": 2}]):
        resp = client.post("/api/mercos/testar-conexao")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["clientes"] == 2


def test_listar_transportadoras(client):
    _auth_as("user")
    with patch.object(MercosService, "listar_transportadoras", return_value=[{"id": 10}]):
        resp = client.get("/api/mercos/transportadoras")
    assert resp.status_code == 200
    assert resp.json()[0]["id"] == 10


def test_listar_politicas_comerciais(client):
    _auth_as("user")
    with patch.object(MercosService, "listar_politicas_comerciais", return_value=[{"id": 20}]):
        resp = client.get("/api/mercos/politicas-comerciais")
    assert resp.status_code == 200
    assert resp.json()[0]["id"] == 20


def test_nao_expoe_tokens_em_erro_mercos(client):
    _auth_as("admin")
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.json.return_value = {
        "mensagem": "erro",
        "ApplicationToken": "SECRET",
        "CompanyToken": "SECRET2",
    }
    mock_resp.text = ""
    mock_resp.headers = {"Authorization": "Bearer x"}
    mock_resp.request = MagicMock(method="POST", path_url="/clientes")

    with patch.object(MercosService, "_request", return_value=mock_resp):
        resp = client.post(
            "/api/mercos/clientes",
            json={"nome": "Cliente Teste"},
        )

    assert resp.status_code == 400
    raw = resp.text
    assert "SECRET" not in raw
    assert "ApplicationToken" not in raw
    assert "CompanyToken" not in raw


def test_cursor_ultima_alteracao_preferido():
    from app.repositories.mercos_sync_repository import MercosSyncRepository

    sync = MercosSyncRepository()
    with patch("app.repositories.mercos_sync_repository.supabase") as sb:
        table = MagicMock()
        sb.table.return_value = table
        table.select.return_value = table
        table.eq.return_value = table
        table.order.return_value = table
        table.limit.return_value = table
        table.execute.return_value = MagicMock(
            data=[{
                "created_at": "2026-01-01T00:00:00",
                "resumo": {"cursor_ultima_alteracao": "2026-07-01T12:00:00"},
            }]
        )
        assert sync.ultima_sincronizacao("orders") == "2026-07-01T12:00:00"
