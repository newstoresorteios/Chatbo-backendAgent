-- F08/F09/F13 ENFORCE. Run only after every API/worker uses the new writer.
-- Reconcile rows created by old writers after PREPARE before enabling enforcement.
-- Rollback application code requires disabling these strict triggers first.
BEGIN;
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

CREATE OR REPLACE FUNCTION public.require_memory_workspace()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path=public,pg_temp AS $$
BEGIN
  IF TG_OP='INSERT' AND NEW.workspace_id IS NULL THEN
    RAISE EXCEPTION 'memory_workspace_required' USING ERRCODE='23514';
  END IF;
  IF TG_OP='UPDATE' AND OLD.workspace_id IS NOT NULL AND NEW.workspace_id IS DISTINCT FROM OLD.workspace_id THEN
    RAISE EXCEPTION 'memory_workspace_immutable' USING ERRCODE='23514';
  END IF;
  IF NEW.workspace_id IS NULL THEN NEW.scope_status := 'quarantined';
  ELSE NEW.scope_status := 'verified'; END IF;
  RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.require_memory_workspace() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.require_memory_workspace() TO service_role;
DO $$ DECLARE name text; BEGIN
  FOREACH name IN ARRAY ARRAY['ai_contact_memories','ai_conversation_summaries','ai_memory_proposals','ai_prompt_compilations'] LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS require_memory_workspace ON public.%I', name);
    EXECUTE format('CREATE TRIGGER require_memory_workspace BEFORE INSERT OR UPDATE ON public.%I FOR EACH ROW EXECUTE FUNCTION public.require_memory_workspace()',name);
  END LOOP;
END $$;

DROP INDEX IF EXISTS public.uq_ai_contact_memory_active_key;
CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_contact_memory_workspace_active_key
  ON public.ai_contact_memories(workspace_id,tenant_id,sender_key,memory_key)
  WHERE status='active' AND workspace_id IS NOT NULL;
-- Remove the historical unique constraint which accidentally joins workspaces.
DO $$ DECLARE item record; BEGIN
  FOR item IN SELECT conname FROM pg_constraint
    WHERE conrelid='public.ai_conversation_summaries'::regclass AND contype='u'
      AND pg_get_constraintdef(oid)='UNIQUE (tenant_id, conversation_key)'
  LOOP EXECUTE format('ALTER TABLE public.ai_conversation_summaries DROP CONSTRAINT %I',item.conname); END LOOP;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_summary_workspace_conversation
  ON public.ai_conversation_summaries(workspace_id,tenant_id,conversation_key) WHERE workspace_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ai_prompt_workspace_inbound
  ON public.ai_prompt_compilations(workspace_id,inbound_id) WHERE response_id IS NULL;

-- Existing prompt links may only be reconstructed when exactly one response owns
-- the same inbound and workspace. Ambiguous retries remain available for review.
WITH candidates AS (
 SELECT p.id, min(r.id) response_id FROM public.ai_prompt_compilations p
 JOIN public.ai_agent_responses r ON r.inbound_id=p.inbound_id AND r.workspace_id=p.workspace_id
 WHERE p.response_id IS NULL AND p.workspace_id IS NOT NULL
 GROUP BY p.id HAVING count(r.id)=1
)
UPDATE public.ai_prompt_compilations p SET response_id=c.response_id FROM candidates c WHERE c.id=p.id;

CREATE OR REPLACE FUNCTION public.preserve_learning_incident()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path=public,pg_temp AS $$
BEGIN
 IF (NEW.tenant_id,NEW.workspace_id,NEW.case_key,NEW.conversation_key,NEW.failure_codes,
     NEW.customer_excerpt,NEW.bad_reply,NEW.correction,NEW.insight_id)
    IS DISTINCT FROM
    (OLD.tenant_id,OLD.workspace_id,OLD.case_key,OLD.conversation_key,OLD.failure_codes,
     OLD.customer_excerpt,OLD.bad_reply,OLD.correction,OLD.insight_id)
 THEN RAISE EXCEPTION 'learning_incident_immutable' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.preserve_learning_incident() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.preserve_learning_incident() TO service_role;
DROP TRIGGER IF EXISTS preserve_learning_incident ON public.ai_learning_cases;
CREATE TRIGGER preserve_learning_incident BEFORE UPDATE ON public.ai_learning_cases
 FOR EACH ROW EXECUTE FUNCTION public.preserve_learning_incident();

CREATE OR REPLACE VIEW public.ai_learning_case_patterns WITH (security_invoker=true) AS
 SELECT tenant_id,workspace_id,code.pattern_key,count(*) incident_count,
   array_agg(id ORDER BY id) case_ids,max(updated_at) latest_at
 FROM public.ai_learning_cases c CROSS JOIN LATERAL jsonb_array_elements_text(c.failure_codes) code(pattern_key)
 GROUP BY tenant_id,workspace_id,code.pattern_key;
REVOKE ALL ON public.ai_learning_case_patterns FROM PUBLIC,anon,authenticated;
GRANT SELECT ON public.ai_learning_case_patterns TO service_role;

-- Both UI approval and agent auto-promotion must carry a current validator report.
-- The application also evaluates near duplicates, negation conflicts and script.
CREATE OR REPLACE FUNCTION public.guard_instruction_activation()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path=public,pg_temp AS $$
DECLARE report jsonb;
BEGIN
 IF NEW.status<>'active' THEN RETURN NEW; END IF;
 IF TG_OP='UPDATE' AND OLD.status='active' AND NEW.instruction_text=OLD.instruction_text THEN RETURN NEW; END IF;
 report := NEW.metadata->'policy_validation';
 IF report IS NULL OR report->>'version'<>'commercial-policy-v1' OR report->>'status'<>'passed'
    OR report->>'instruction_hash' IS DISTINCT FROM NEW.instruction_hash
 THEN RAISE EXCEPTION 'instruction_policy_validation_required' USING ERRCODE='23514'; END IF;
 IF NEW.workspace_id IS NULL THEN RAISE EXCEPTION 'instruction_workspace_required' USING ERRCODE='23514'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended(NEW.tenant_id || ':' || NEW.workspace_id::text,0));
 IF EXISTS (SELECT 1 FROM public.ai_agent_instruction_extensions e
   WHERE e.workspace_id=NEW.workspace_id AND e.tenant_id=NEW.tenant_id AND e.id<>NEW.id
     AND e.status='active' AND (e.expires_at IS NULL OR e.expires_at>now())
     AND lower(regexp_replace(e.instruction_text,'[[:space:][:punct:]]','','g'))=
         lower(regexp_replace(NEW.instruction_text,'[[:space:][:punct:]]','','g')))
 THEN RAISE EXCEPTION 'duplicate_active_instruction' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.guard_instruction_activation() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.guard_instruction_activation() TO service_role;
DROP TRIGGER IF EXISTS guard_instruction_activation ON public.ai_agent_instruction_extensions;
CREATE TRIGGER guard_instruction_activation BEFORE INSERT OR UPDATE ON public.ai_agent_instruction_extensions
 FOR EACH ROW EXECUTE FUNCTION public.guard_instruction_activation();

-- Retain application-only access to all existing sequences for these tables.
DO $$ DECLARE name text; sequence_name text; BEGIN
 FOREACH name IN ARRAY ARRAY['ai_contact_memories','ai_conversation_summaries','ai_memory_proposals','ai_prompt_compilations'] LOOP
  sequence_name := pg_get_serial_sequence('public.'||name,'id');
  IF sequence_name IS NOT NULL THEN
   EXECUTE format('REVOKE ALL ON SEQUENCE %s FROM PUBLIC,anon,authenticated',sequence_name);
   EXECUTE format('GRANT USAGE,SELECT ON SEQUENCE %s TO service_role',sequence_name);
  END IF;
 END LOOP;
END $$;
NOTIFY pgrst, 'reload schema';
COMMIT;
