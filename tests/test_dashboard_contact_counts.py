from app.services.dashboard_service import DashboardService


def test_dashboard_counts_one_row_per_contact_and_only_confirmed_handoffs(monkeypatch):
    service = DashboardService()
    monkeypatch.setattr(
        service.contact_inbox,
        "listar",
        lambda workspace_id, limit: [
            {"current_session": {"status": "active"}},
            {"current_session": {"status": "closed"}},
            {"current_session": {"status": "waiting"}},
            {
                "current_session": {
                    "status": "waiting",
                    "handoff_requested_at": "2026-09-16T12:00:00Z",
                    "handoff_reason": "customer_requested_human",
                }
            },
        ],
    )

    assert service._contar_conversas_por_status("workspace-1") == {
        "active": 2,
        "waiting": 1,
        "closed": 1,
    }
