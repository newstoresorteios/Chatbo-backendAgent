-- F08/F09/F13 PREPARE. Compatible with the currently deployed version.
-- Apply this first, deploy the scoped writer/validator release, drain old workers,
-- then apply memory_scope_learning_policy_enforce.sql. No strict triggers here.
-- Backfill uses only recorded inbound/response ownership; never tenant-name guesses.
BEGIN;

CREATE TABLE IF NOT EXISTS public.ai_memory_scope_migration_audit (
  table_name text NOT NULL,
  record_id bigint NOT NULL,
  action text NOT NULL CHECK (action IN ('backfilled', 'quarantined')),
  workspace_id uuid,
  candidate_count integer NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (table_name, record_id)
);
ALTER TABLE public.ai_memory_scope_migration_audit ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.ai_memory_scope_migration_audit FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.ai_memory_scope_migration_audit TO service_role;

DO $$
DECLARE target record;
BEGIN
  FOR target IN SELECT * FROM (VALUES
    ('ai_contact_memories', 'source_inbound_id', 'source_response_id'),
    ('ai_conversation_summaries', 'last_inbound_id', 'last_response_id'),
    ('ai_memory_proposals', 'inbound_id', 'response_id'),
    ('ai_prompt_compilations', 'inbound_id', 'response_id')
  ) AS x(table_name, inbound_column, response_column)
  LOOP
    EXECUTE format('ALTER TABLE public.%I ADD COLUMN IF NOT EXISTS workspace_id uuid', target.table_name);
    EXECUTE format('ALTER TABLE public.%I ADD COLUMN IF NOT EXISTS scope_status text NOT NULL DEFAULT ''verified''', target.table_name);
    EXECUTE format($sql$
      INSERT INTO public.ai_memory_scope_migration_audit(table_name,record_id,action,workspace_id,candidate_count)
      SELECT %L, m.id, CASE WHEN count(DISTINCT c.workspace_id)=1 THEN 'backfilled' ELSE 'quarantined' END,
        CASE WHEN count(DISTINCT c.workspace_id)=1 THEN min(c.workspace_id::text)::uuid END,
        count(DISTINCT c.workspace_id)
      FROM public.%I m
      LEFT JOIN LATERAL (
        SELECT i.workspace_id FROM public.ai_inbound_messages i WHERE i.id=m.%I
        UNION
        SELECT r.workspace_id FROM public.ai_agent_responses r WHERE r.id=m.%I
      ) c ON true
      WHERE m.workspace_id IS NULL
      GROUP BY m.id ON CONFLICT(table_name,record_id) DO NOTHING
    $sql$, target.table_name, target.table_name, target.inbound_column, target.response_column);
    EXECUTE format($sql$
      UPDATE public.%I m SET workspace_id=a.workspace_id,
        scope_status=CASE WHEN a.action='backfilled' THEN 'verified' ELSE 'quarantined' END
      FROM public.ai_memory_scope_migration_audit a
      WHERE a.table_name=%L AND a.record_id=m.id AND m.workspace_id IS NULL
    $sql$, target.table_name, target.table_name);
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', target.table_name);
    EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC, anon, authenticated', target.table_name);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON public.%I TO service_role', target.table_name);
  END LOOP;
END $$;

ALTER TABLE public.ai_learning_cases ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.ai_learning_cases FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON public.ai_learning_cases TO service_role;
-- Add the future conflict targets during PREPARE; preserve historical keys until
-- all old writers are drained. Their removal belongs to ENFORCE.
CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_contact_memory_workspace_active_key
  ON public.ai_contact_memories(workspace_id,tenant_id,sender_key,memory_key)
  WHERE status='active' AND workspace_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_summary_workspace_conversation
  ON public.ai_conversation_summaries(workspace_id,tenant_id,conversation_key) WHERE workspace_id IS NOT NULL;
NOTIFY pgrst, 'reload schema';
COMMIT;
