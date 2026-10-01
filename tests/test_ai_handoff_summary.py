from unittest.mock import MagicMock, patch

from app.services.ai_handoff_summary import enrich_handoff_summaries


def test_summary_reaches_authorized_operator_even_when_delivery_failed():
    client = MagicMock()
    rows = client.table.return_value.select.return_value.eq.return_value.in_.return_value
    rows.execute.return_value.data = [{'id': 10, 'workspace_id': 'w', 'handoff_required': True,
        'handoff': {'confirmed': True, 'consent_reason': 'customer_requested_human',
                    'summary': {'version': 1, 'pending_action': 'awaiting_shipping_zipcode',
                                'consent': {'confirmed': True}, 'internal_secret': 'never return'}}}]
    original = {'id': 'central', 'externalId': 'ai-out-10', 'sender': 'ai', 'status': 'failed', 'content': 'Encaminhando'}
    with patch('app.services.ai_handoff_summary.supabase', client):
        result = enrich_handoff_summaries([original], 'w')
    assert result[0]['handoffSummary']['pending_action'] == 'awaiting_shipping_zipcode'
    assert 'internal_secret' not in result[0]['handoffSummary']
    assert result[0]['status'] == 'failed' and original.get('handoffSummary') is None
    client.table.return_value.select.return_value.eq.assert_called_once_with('workspace_id', 'w')


def test_foreign_or_unconfirmed_summary_is_not_attached():
    message = {'id': 'ai-out-10', 'sender': 'ai'}
    client = MagicMock()
    rows = client.table.return_value.select.return_value.eq.return_value.in_.return_value
    for workspace, confirmed in [('other', True), ('w', False)]:
        rows.execute.return_value.data = [{'id': 10, 'workspace_id': workspace, 'handoff_required': True,
            'handoff': {'confirmed': confirmed, 'consent_reason': 'customer_requested_human', 'summary': {'version': 1}}}]
        with patch('app.services.ai_handoff_summary.supabase', client):
            assert enrich_handoff_summaries([message], 'w') == [message]
    with patch('app.services.ai_handoff_summary.supabase', client):
        client.reset_mock()
        assert enrich_handoff_summaries([message], None) == [message]
        client.table.assert_not_called()
