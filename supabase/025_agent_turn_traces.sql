-- Isolamento e índice para o painel de execuções do NSAgent.
-- O Supabase CLI não está instalado neste workspace; migration criada no padrão existente.

ALTER TABLE public.ai_agent_responses
  ADD COLUMN IF NOT EXISTS workspace_id UUID REFERENCES public.workspaces(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_ai_agent_responses_workspace_created_at
  ON public.ai_agent_responses(workspace_id, created_at DESC);

-- Recupera traces antigos que já carregavam o workspace dentro do metadata seguro.
WITH candidates AS MATERIALIZED (
  SELECT
    response.id,
    CASE
      WHEN response.provider_response #>> '{_agent_metadata,persona_runtime,workspace_id}'
        ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
      THEN (response.provider_response #>> '{_agent_metadata,persona_runtime,workspace_id}')::UUID
    END AS workspace_id
  FROM public.ai_agent_responses response
  WHERE response.workspace_id IS NULL
)
UPDATE public.ai_agent_responses response
SET workspace_id = candidates.workspace_id
FROM candidates
JOIN public.workspaces workspace ON workspace.id = candidates.workspace_id
WHERE response.id = candidates.id
  AND candidates.workspace_id IS NOT NULL;

ALTER TABLE public.ai_agent_responses ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ai_inbound_messages ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.ai_agent_responses FROM anon, authenticated;
REVOKE ALL ON TABLE public.ai_inbound_messages FROM anon, authenticated;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.ai_agent_responses TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.ai_inbound_messages TO service_role;
