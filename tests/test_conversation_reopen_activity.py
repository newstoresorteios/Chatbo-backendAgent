import pytest

from app.services.ai_conversas_bridge import _new_customer_activity_patch


def conversation(**changes):
    return {"status": "closed", "bot_activated": True,
            "last_message_at": "2026-09-25T03:00:00Z", **changes}


def test_new_customer_message_reopens_bot_enabled_conversation():
    assert _new_customer_activity_patch(conversation(), [
        {"created_at": "2026-09-25T03:47:03Z"}
    ]) == {"status": "active"}


@pytest.mark.parametrize("changes", [
    {"assigned_to": "operator"}, {"bot_activated": False},
    {"merged_into": "other-session"}, {"status": "active"},
])
def test_preserves_human_and_merged_sessions(changes):
    assert _new_customer_activity_patch(conversation(**changes), [
        {"created_at": "2026-09-25T03:47:03Z"}
    ]) == {}


@pytest.mark.parametrize("created", [None, "invalid", "2026-09-25T03:00:00Z", "2026-09-24T23:00:00-03:00"])
def test_history_replay_does_not_reopen_conversation(created):
    assert _new_customer_activity_patch(conversation(), [{"created_at": created}]) == {}


def test_delayed_inbound_before_manual_close_does_not_reopen():
    assert _new_customer_activity_patch(conversation(updated_at="2026-09-25T04:00:00Z"), [
        {"created_at": "2026-09-25T03:47:03Z"}
    ]) == {}
