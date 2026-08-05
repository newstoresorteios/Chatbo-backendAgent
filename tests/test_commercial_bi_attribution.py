from app.services.commercial_bi_service import CommercialBiService


def test_attribute_orders_marks_chatbo_by_phone():
    service = CommercialBiService()
    orders = [
        {"id": 1, "total": 100, "status": "paid", "customer_phone": "11999998888", "customer_email": "a@x.com"},
        {"id": 2, "total": 50, "status": "delivered", "customer_phone": "11888887777", "customer_email": "b@x.com"},
    ]
    attributed = service._attribute_orders(orders, {"11999998888"}, set())
    assert attributed[0]["source"] == "chatbo"
    assert attributed[1]["source"] == "tray"


def test_build_kpis_by_source():
    service = CommercialBiService()
    attributed = [
        {"id": "1", "total": 100.0, "status": "processing", "source": "tray"},
        {"id": "2", "total": 40.0, "status": "delivered", "source": "chatbo"},
        {"id": "3", "total": 10.0, "status": "cancelled", "source": "tray"},
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
    assert kpis["bySource"]["chatbo"] == 40.0
    assert kpis["bySource"]["tray"] == 100.0
