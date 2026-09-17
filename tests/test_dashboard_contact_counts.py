from app.services.dashboard_service import DashboardService
from datetime import datetime, timezone


def test_dashboard_counts_one_row_per_contact_and_only_confirmed_handoffs(monkeypatch):
    service = DashboardService()
    monkeypatch.setattr(
        service.contact_inbox,
        "listar",
        lambda workspace_id, limit: [
            {"last_message_at": datetime.now(timezone.utc).isoformat(), "current_session": {"status": "active"}},
            {"last_message_at": datetime.now(timezone.utc).isoformat(), "current_session": {"status": "closed"}},
            {"last_message_at": datetime.now(timezone.utc).isoformat(), "current_session": {"status": "waiting"}},
            {
                "last_message_at": datetime.now(timezone.utc).isoformat(),
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
