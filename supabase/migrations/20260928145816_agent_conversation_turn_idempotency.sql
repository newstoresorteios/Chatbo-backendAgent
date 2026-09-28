ALTER TABLE public.ai_agent_responses
  ADD COLUMN IF NOT EXISTS source_event_key text;

CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_agent_responses_workspace_source_event
  ON public.ai_agent_responses (workspace_id, source_event_key)
  WHERE workspace_id IS NOT NULL AND source_event_key IS NOT NULL;

COMMENT ON COLUMN public.ai_agent_responses.source_event_key IS
  'Idempotency key supplied by a trusted agent ingress, scoped to workspace.';
