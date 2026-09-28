from app.services.mercos_adaptor_client import MercosAdaptorClient


def test_mercos_adaptor_uses_internal_api_key_header():
    client = MercosAdaptorClient("https://mercos.test", "internal-key")

    assert client._headers() == {
        "x-api-key": "internal-key",
        "Accept": "application/json",
    }


def test_mercos_adaptor_maps_resources_and_reuses_order_items(monkeypatch):
    client = MercosAdaptorClient("https://mercos.test", "internal-key")
    calls = []

    def fake_get(path, params=None):
        calls.append((path, params))
        if path == "v1/products":
            return {"data": [{"id": 1}, {"id": 2}]}
        if path == "v1/orders":
            return {
                "data": [{
                    "id": 10,
                    "data_emissao": "2026-09-20",
                    "cliente_nome_fantasia": "Cliente",
                    "cliente_email": "cliente@example.com",
                    "cliente_telefone": "11999999999",
                    "itens": [{
                        "produto_id": 20,
                        "produto_nome": "Produto",
                        "quantidade": 2,
                        "preco_liquido": 19.9,
                    }],
                }]
            }
        raise AssertionError(path)

    monkeypatch.setattr(client, "_get", fake_get)

    assert client.list_products(page=1, limit=1) == [{"id": 1}]
    assert client.list_products(page=2, limit=1) == [{"id": 2}]
    orders = client.list_orders(page=1, limit=50)
    assert orders[0]["date"] == "2026-09-20"
    assert orders[0]["customer_email"] == "cliente@example.com"
    assert client.order_complete("10") == {
        "products": [{
            "product_id": 20,
            "name": "Produto",
            "quantity": 2,
            "price": 19.9,
        }]
    }
    assert [path for path, _ in calls].count("v1/products") == 1
    assert [path for path, _ in calls].count("v1/orders") == 1
