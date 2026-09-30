"""Read-only commercial projection from customer messages, scoped by workspace.

Stages are observed intent, not inferred orders or revenue. Historical stages
mean signals actually observed in persisted messages, not CRM transition dates.
"""
import re
import unicodedata
from datetime import datetime, timezone

from fastapi import HTTPException
from app.services.supabase_service import supabase
from app.services.contact_inbox_service import map_contact

STAGES = {'contact': 'Contato / qualificação', 'interest': 'Interesse comercial',
          'high_intent': 'Quente — agir em até 24h', 'follow_up': 'Acompanhar / reativar',
          'post_sale': 'Pós-venda', 'closed': 'Atendimento encerrado', 'lost': 'Sem interesse'}


def intent_stage(text):
    text = ''.join(c for c in unicodedata.normalize('NFKD', text.lower()) if not unicodedata.combining(c))
    if re.search(r'nao (quero|vou) (comprar|fechar)|nao tenho interesse|desisti da compra', text):
        return 'lost'
    if re.search(r'meu pedido|rastre|despach|ja (comprei|paguei)|status.*pedido|pedido.*(cheg|envi)|garantia|assistencia|devolu|troca', text):
        return 'post_sale'
    if re.search(r'pronta[ -]+entrega|quero (comprar|fechar|pagar)|vou (comprar|levar)|como (compro|pago)|link.*pagamento|manda.*pix|pode reservar', text):
        return 'high_intent'
    if re.search(r'preco|valor|orcamento|disponiv|estoque|quanto|parcela|frete|comprar', text):
        return 'interest'
    return None


def project_lead(group, messages, *, now=None):
    contact = map_contact(group)
    stage = 'contact'
    history = {'contact'}
    evidence = None
    for message in sorted(messages, key=lambda m: (m.get('created_at') or '', str(m.get('id') or ''))):
        if message.get('sender') != 'customer':
            continue
        observed = intent_stage(str(message.get('content') or ''))
        if observed:
            # A price follow-up does not erase an explicit purchase decision.
            if not (stage == 'high_intent' and observed == 'interest'):
                stage = observed
                evidence = message
            history.add(observed)
    if contact['status'] == 'closed':
        stage = 'closed'
        history.add('closed')
    score = {'contact': 30, 'interest': 65, 'high_intent': 90, 'post_sale': 15, 'closed': 10, 'lost': 0}[stage]
    evidence_at = (evidence or {}).get('created_at')
    age_hours = None
    if evidence_at:
        try:
            observed_at = datetime.fromisoformat(evidence_at.replace('Z', '+00:00'))
            if observed_at.tzinfo is None:
                observed_at = observed_at.replace(tzinfo=timezone.utc)
            age_hours = max(0, ((now or datetime.now(timezone.utc)) - observed_at).total_seconds() / 3600)
        except (ValueError, TypeError):
            pass
    if stage == 'high_intent' and (age_hours is None or age_hours >= 24):
        stage = 'follow_up'
        score = 60 if age_hours is not None and age_hours < 168 else 35
    elif stage == 'interest' and (age_hours is None or age_hours >= 168):
        stage = 'follow_up'
        score = 35
    history.add(stage)
    return {**contact, 'score': score, 'label': 'Quente' if score >= 75 else 'Morno' if score >= 50 else 'Frio',
            'stage': stage, 'stageName': STAGES[stage], 'observedStages': sorted(history),
            'reason': STAGES[stage] if evidence else 'Sem sinal comercial confirmado no histórico carregado',
            'evidence': str((evidence or {}).get('content') or '')[:300], 'evidenceAt': evidence_at,
            'intentAgeHours': round(age_hours, 1) if age_hours is not None else None,
            'lastInteraction': contact['lastMessageAt'],
            'nextAction': 'Respeitar recusa; não insistir' if stage == 'lost' else 'Atender pós-venda' if stage == 'post_sale' else 'Agir agora: atribuir ao comercial' if stage == 'high_intent' else 'Reavaliar interesse antes de abordar' if stage == 'follow_up' else 'Qualificar atendimento'}


def list_commercial_leads(workspace_id, page=1, page_size=100):
    if not workspace_id:
        raise HTTPException(403, 'Empresa não resolvida')
    start = (page - 1) * page_size
    result = (supabase.table('conversation_contact_inbox').select('*', count='exact')
              .eq('workspace_id', workspace_id).order('id').range(start, start + page_size - 1).execute())
    groups = result.data or []
    ids = list({str(s) for g in groups for s in g['session_ids']})
    by_session = {}
    complete = True
    sessions = []
    for offset in range(0, len(ids), 100):
        sessions.extend(supabase.table('conversas').select('id,external_thread_id,channel')
                        .eq('workspace_id', workspace_id).in_('id', ids[offset:offset + 100]).execute().data or [])
        # Cap work per request and explicitly expose truncated historical evidence.
        for message_page in range(20):
            messages = (supabase.table('mensagens').select('id,conversa_id,sender,content,created_at')
                        .or_(f'workspace_id.eq.{workspace_id},workspace_id.is.null')
                        .in_('conversa_id', ids[offset:offset + 100]).eq('sender', 'customer')
                        .order('created_at', desc=True).order('id')
                        .range(message_page * 1000, message_page * 1000 + 999).execute().data or [])
            for message in messages:
                by_session.setdefault(str(message['conversa_id']), []).append(message)
            if len(messages) < 1000:
                break
        else:
            complete = False
    # Inbox messages are materialized only after opening a conversation. Include
    # the original inbound events so unopened hot leads are not silently missed.
    threads = list({s['external_thread_id'] for s in sessions if s.get('external_thread_id')})
    session_by_thread = {}
    for session in sessions:
        session_by_thread.setdefault((session.get('external_thread_id'), session.get('channel')), []).append(str(session['id']))
    for offset in range(0, len(threads), 100):
        for inbound_page in range(20):
            inbounds = (supabase.table('ai_inbound_messages').select('id,conversation_id,channel,text,created_at')
                        .eq('workspace_id', workspace_id).in_('conversation_id', threads[offset:offset + 100])
                        .order('created_at', desc=True).order('id')
                        .range(inbound_page * 1000, inbound_page * 1000 + 999).execute().data or [])
            for row in inbounds:
                for session_id in session_by_thread.get((row['conversation_id'], row['channel']), []):
                    by_session.setdefault(session_id, []).append({
                        'id': f"ai-in-{row['id']}", 'sender': 'customer', 'content': row.get('text'),
                        'created_at': row.get('created_at'),
                    })
            if len(inbounds) < 1000:
                break
        else:
            complete = False
    leads = [project_lead(g, [m for s in g['session_ids'] for m in by_session.get(str(s), [])]) for g in groups]
    from app.services.conversas_service import ConversasService
    users = ConversasService()._users_index()
    for lead in leads:
        lead['assignedName'] = (users.get(str(lead.get('assignedTo'))) or {}).get('name')
    return {'items': leads, 'total': result.count or 0, 'page': page,
            'hasMore': start + len(groups) < (result.count or 0), 'historyComplete': complete,
            'stages': STAGES}
