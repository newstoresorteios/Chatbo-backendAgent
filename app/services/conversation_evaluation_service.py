from app.services.supabase_service import supabase


def list_conversation_evaluations(workspace_id: str) -> dict:
    rows = (supabase.table('ai_conversation_evaluation_runs')
            .select('id,case_id,status,versions,result,created_at,finished_at')
            .eq('workspace_id', workspace_id).order('created_at', desc=True).limit(30).execute().data or [])
    items = []
    for row in rows:
        result = row.get('result') or {}
        replay = result.get('replay') or {}
        repair = result.get('repair') or {}
        items.append({
            'id': row['id'], 'caseId': row['case_id'], 'status': row['status'],
            'createdAt': row.get('created_at'), 'versions': row.get('versions') or {},
            'question': result.get('input'), 'historicalReply': result.get('historical_reply'),
            'replayReply': replay.get('reply'), 'outcome': result.get('outcome'),
            'generativeExercised': replay.get('generative_exercised'),
            'assessment': result.get('assessment'), 'error': result.get('error') or replay.get('error'),
            'path': (replay.get('metadata') or {}).get('path') or {},
            'tools': [{'tool': c.get('tool'), 'arguments': c.get('arguments'),
                       'error': (c.get('result') or {}).get('error'), 'elapsed_ms': c.get('elapsed_ms')}
                      for c in replay.get('tools') or []],
            'repair': {k: repair.get(k) for k in ('status','applied','instruction','reason')},
        })
    return {'items': items}
