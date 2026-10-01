"""Read persisted handoff briefs for the authorized operator's transcript."""
import logging
import re

from app.services.supabase_service import supabase

logger = logging.getLogger(__name__)


def enrich_handoff_summaries(messages: list[dict], workspace_id: str | None) -> list[dict]:
    if not workspace_id:
        return messages
    ids = {match[1] for message in messages
           if message.get('sender') == 'ai'
           and (match := re.fullmatch(r'ai-out-(\d+)', str(message.get('externalId') or message.get('id') or '')))}
    if not ids:
        return messages
    try:
        rows = (supabase.table('ai_agent_responses')
                .select('id,workspace_id,handoff_required,handoff:provider_response->_agent_metadata->handoff')
                .eq('workspace_id', workspace_id).in_('id', list(ids)).execute().data or [])
        summaries = {}
        for row in rows:
            handoff = row.get('handoff')
            if (str(row.get('workspace_id')) != str(workspace_id) or str(row.get('id')) not in ids
                    or row.get('handoff_required') is not True or not isinstance(handoff, dict)
                    or handoff.get('confirmed') is not True
                    or handoff.get('consent_reason') not in {'customer_requested_human', 'customer_accepted_handoff_offer'}):
                continue
            summary = handoff.get('summary')
            if isinstance(summary, dict) and summary.get('version') == 1:
                summaries[f"ai-out-{row['id']}"] = {key: summary.get(key) for key in (
                    'version', 'customer_request', 'objective', 'constraints', 'product_focus', 'order_focus',
                    'pending_action', 'pending_question', 'delivery_requirement', 'known_checkout_fields', 'consent')}
        return [{**message, 'handoffSummary': summaries[key]}
                if (key := str(message.get('externalId') or message.get('id'))) in summaries else message
                for message in messages]
    except Exception as exc:
        logger.warning('Handoff summary unavailable (%s)', type(exc).__name__)
        return messages
