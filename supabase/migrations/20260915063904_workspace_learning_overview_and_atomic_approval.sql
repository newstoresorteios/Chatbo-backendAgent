CREATE OR REPLACE FUNCTION public.workspace_learning_overview(p_workspace_id uuid, p_tenant_id text)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path=public,pg_temp AS $$
WITH insights AS MATERIALIZED (
 SELECT * FROM ai_learning_insights WHERE workspace_id=p_workspace_id AND tenant_id=p_tenant_id AND status='pending_review'
), extensions AS MATERIALIZED (
 SELECT * FROM ai_agent_instruction_extensions WHERE workspace_id=p_workspace_id AND tenant_id=p_tenant_id AND status IN ('pending_review','active')
), reviews AS MATERIALIZED (
 SELECT id,response_id,channel,outcome,failure_codes,left(customer_text,240) AS customer_text,
 left(agent_reply,240) AS agent_reply,created_at FROM ai_attendance_reviews
 WHERE workspace_id=p_workspace_id AND tenant_id=p_tenant_id ORDER BY created_at DESC,id DESC LIMIT 30
), cases AS MATERIALIZED (
 SELECT id,case_key,failure_codes,left(customer_excerpt,400) AS customer_excerpt,
 left(bad_reply,400) AS bad_reply,left(correction,800) AS correction,status,importance,insight_id,updated_at
 FROM ai_learning_cases WHERE workspace_id=p_workspace_id AND tenant_id=p_tenant_id AND status='active'
), daily AS (
 SELECT count(*) AS total,count(*) FILTER(WHERE jsonb_typeof(failure_codes)='array' AND failure_codes <> '[]'::jsonb) AS failed
 FROM ai_attendance_reviews WHERE workspace_id=p_workspace_id AND tenant_id=p_tenant_id AND created_at>=now()-interval '24 hours'
)
SELECT jsonb_build_object(
 'pendingInsights',coalesce((SELECT jsonb_agg(to_jsonb(t)) FROM (SELECT * FROM insights ORDER BY created_at DESC,id DESC LIMIT 100)t),'[]'),
 'pendingExtensions',coalesce((SELECT jsonb_agg(to_jsonb(t)) FROM (SELECT * FROM extensions WHERE status='pending_review' ORDER BY created_at DESC,id DESC LIMIT 100)t),'[]'),
 'activeExtensions',coalesce((SELECT jsonb_agg(to_jsonb(t)) FROM (SELECT * FROM extensions WHERE status='active' ORDER BY created_at DESC,id DESC LIMIT 50)t),'[]'),
 'recentReviews',coalesce((SELECT jsonb_agg(to_jsonb(t)) FROM reviews t),'[]'),
 'activeCases',coalesce((SELECT jsonb_agg(to_jsonb(t)) FROM (SELECT * FROM cases ORDER BY importance DESC,id DESC LIMIT 20)t),'[]'),
 'counts',jsonb_build_object('pendingInsights',(SELECT count(*) FROM insights),
 'pendingExtensions',(SELECT count(*) FROM extensions WHERE status='pending_review'),
 'activeExtensions',(SELECT count(*) FROM extensions WHERE status='active'),
 'reviewsLast24h',(SELECT total FROM daily),'failuresLast24h',(SELECT failed FROM daily),'activeCases',(SELECT count(*) FROM cases)),
 'configurationVersion',(SELECT config_version FROM workspace_agents WHERE workspace_id=p_workspace_id AND agent_type='nsagent' AND status='active'),
 'generatedAt',now());
$$;

CREATE OR REPLACE FUNCTION public.approve_workspace_instruction_extension(p_workspace_id uuid,p_tenant_id text,p_extension_id bigint,p_actor text)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public,pg_temp AS $$
DECLARE chosen ai_agent_instruction_extensions;
BEGIN
 PERFORM pg_advisory_xact_lock(hashtextextended(p_tenant_id || ':' || p_workspace_id::text,0));
 SELECT * INTO chosen FROM ai_agent_instruction_extensions WHERE id=p_extension_id AND workspace_id=p_workspace_id AND tenant_id=p_tenant_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'extension_not_found' USING ERRCODE='P0002'; END IF;
 IF chosen.status='active' THEN RETURN to_jsonb(chosen); END IF;
 IF chosen.status NOT IN ('pending_review','rejected') THEN RAISE EXCEPTION 'extension_status_conflict' USING ERRCODE='23514'; END IF;
 UPDATE ai_agent_instruction_extensions SET status='superseded',updated_at=now()
 WHERE workspace_id=p_workspace_id AND tenant_id=p_tenant_id AND scope=chosen.scope
 AND scope_key_norm=chosen.scope_key_norm AND extension_key=chosen.extension_key AND status='active' AND id<>chosen.id;
 UPDATE ai_agent_instruction_extensions SET status='active',approved_by=p_actor,approved_at=now(),updated_at=now(),
 rejected_by=NULL,rejected_at=NULL,rejection_reason=NULL WHERE id=chosen.id RETURNING * INTO chosen;
 UPDATE ai_learning_insights SET status='applied',applied_extension_id=chosen.id,reviewed_at=now(),updated_at=now()
 WHERE workspace_id=p_workspace_id AND tenant_id=p_tenant_id
 AND (applied_extension_id=chosen.id OR id::text=chosen.metadata->>'insight_id');
 RETURN to_jsonb(chosen);
END;
$$;
REVOKE ALL ON FUNCTION public.workspace_learning_overview(uuid,text) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.approve_workspace_instruction_extension(uuid,text,bigint,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.workspace_learning_overview(uuid,text),public.approve_workspace_instruction_extension(uuid,text,bigint,text) TO service_role;
CREATE INDEX IF NOT EXISTS ai_attendance_reviews_workspace_time_idx ON public.ai_attendance_reviews(workspace_id,tenant_id,created_at DESC);
