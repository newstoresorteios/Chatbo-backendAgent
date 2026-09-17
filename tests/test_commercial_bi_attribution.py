from app.services.commercial_bi_service import CommercialBiService


def test_attribute_orders_marks_chatbo_by_phone():
    service = CommercialBiService()
    orders = [
        {"id": 1, "total": 100, "status": "paid", "customer_phone": "11999998888", "customer_email": "a@x.com"},
        {"id": 2, "total": 50, "status": "delivered", "customer_phone": "11888887777", "customer_email": "b@x.com"},
    ]
    attributed = service._attribute_orders(
        orders,
        {"11999998888"},
        set(),
        {"1": {"11999998888"}},
        {},
    )
    assert attributed[0]["source"] == "chatbo"
    assert attributed[1]["source"] == "tray"


def test_attribute_orders_rejects_phone_only_match_without_commerce_evidence():
    service = CommercialBiService()
    attributed = service._attribute_orders(
        [{"id": 25894, "session_id": "external-cart", "customer_phone": "43998640480"}],
        {"43998640480"},
        {},
        {},
        {},
    )

    assert attributed[0]["source"] == "tray"
    assert attributed[0]["attributionReason"] is None


def test_attribute_orders_accepts_verified_cart_session_for_same_contact():
    service = CommercialBiService()
    attributed = service._attribute_orders(
        [{"id": 100, "session_id": "chatbo-cart", "customer_phone": "11999998888"}],
        {"11999998888"},
        set(),
        {},
        {"chatbo-cart": {"11999998888"}},
    )

    assert attributed[0]["source"] == "chatbo"
    assert attributed[0]["attributionReason"] == "verified_commerce_link"


def test_build_kpis_by_source():
    service = CommercialBiService()
    attributed = [
        {"id": "1", "total": 100.0, "status": "processing", "source": "tray"},
        {"id": "2", "total": 40.0, "status": "delivered", "source": "chatbo"},
        {"id": "3", "total": 10.0, "status": "cancelled", "source": "tray"},
        {"id": "4", "total": 20.0, "status": "pending", "source": "tray"},
    ]
    kpis = service._build_kpis(
        attributed,
        active_conversations=3,
        waiting_queue=1,
        customers_count=10,
        products_count=5,
    )
    assert kpis["pedidosConfirmados"] == 2
    assert kpis["receitaVendida"] == 140.0
    assert kpis["pipelineEmAberto"] == 20.0
    assert kpis["oportunidadesEmAberto"] == 1
    assert kpis["pedidosEntregues"] == 1
    assert kpis["dataScope"] == "chatbo_current_month"
    assert "bySource" not in kpis


def test_entities_only_include_customers_from_attributed_chatbo_orders():
    service = CommercialBiService()
    entities = service._entities([
        {
            "id": "order-1",
            "total": 250.0,
            "status": "shipped",
            "source": "chatbo",
            "customerName": "Cliente ChatBô",
            "customerEmail": None,
            "customerPhone": "5511999999999",
            "createdAt": "2026-09-10T12:00:00Z",
        }
    ])
    assert len(entities["customers"]) == 1
    assert entities["customers"][0]["source"] == "chatbo"
    assert entities["products"] == []
    assert len(entities["orders"]) == 1


def test_enrich_order_items_exposes_clean_product_details():
    class FakeClient:
        def order_complete(self, order_id):
            assert order_id == "25894"
            return {
                "products": [
                    {
                        "product_id": 14518,
                        "name": "Kit De Reparo Relojoeiro (Disponibilidade: Disponível em 30 dias úteis)<br />",
                        "quantity": 1,
                        "price": "299.99",
                    }
                ]
            }

    service = CommercialBiService()
    orders = service._enrich_order_items(FakeClient(), [{"id": "25894", "total": 299.99}])

    assert orders[0]["itemsCount"] == 1
    assert orders[0]["items"] == [
        {
            "productId": "14518",
            "name": "Kit De Reparo Relojoeiro",
            "quantity": 1,
            "price": 299.99,
        }
    ]
