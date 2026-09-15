-- Production af98c957ad09 verified: authenticated drain loads persona 17 and
-- workspace configuration version 1; unauthorized calls return 401.
DO $$
BEGIN
 IF NOT EXISTS (
   SELECT FROM public.ai_agent_persona_versions p
   JOIN public.workspace_agents wa ON wa.workspace_id=p.workspace_id
   WHERE p.status='active' AND wa.agent_type='nsagent' AND wa.status='active'
     AND wa.config_version > 0
 ) THEN RAISE EXCEPTION 'queue_dispatch_requires_published_workspace_configuration'; END IF;
 IF NOT EXISTS (SELECT FROM vault.secrets WHERE name='nsagent_queue_dispatch')
 THEN RAISE EXCEPTION 'queue_dispatch_secret_missing'; END IF;
 UPDATE agent_private.queue_dispatch_settings SET enabled=true WHERE singleton;
END $$;
