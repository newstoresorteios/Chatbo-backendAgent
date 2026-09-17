from app.services.tray_adaptor_client import TrayAdaptorClient


def test_hydrate_order_customers_attaches_detail_by_customer_id(monkeypatch):
    client = TrayAdaptorClient("https://adapter.test", "token")
    monkeypatch.setattr(
        client,
        "customer_detail",
        lambda customer_id: {"id": customer_id, "cellphone": "5511999999999"},
    )

    rows = client._hydrate_order_customers([
        {"id": "order-1", "customer_id": "customer-1", "date": "2026-09-10"},
    ])

    assert rows[0]["Customer"]["id"] == "customer-1"
    assert rows[0]["Customer"]["cellphone"] == "5511999999999"
