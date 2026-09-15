-- Isola o aprendizado continuo por workspace e prepara o painel operacional.
-- Criado manualmente porque a Supabase CLI nao esta disponivel neste ambiente.

ALTER TABLE public.ai_attendance_reviews
  ADD COLUMN IF NOT EXISTS workspace_id UUID REFERENCES public.workspaces(id) ON DELETE SET NULL;
ALTER TABLE public.ai_learning_insights
  ADD COLUMN IF NOT EXISTS workspace_id UUID REFERENCES public.workspaces(id) ON DELETE SET NULL;
ALTER TABLE public.ai_learning_cases
  ADD COLUMN IF NOT EXISTS workspace_id UUID REFERENCES public.workspaces(id) ON DELETE SET NULL;
ALTER TABLE public.ai_agent_instruction_extensions
  ADD COLUMN IF NOT EXISTS workspace_id UUID REFERENCES public.workspaces(id) ON DELETE SET NULL;

UPDATE public.ai_attendance_reviews review
SET workspace_id = response.workspace_id
FROM public.ai_agent_responses response
WHERE review.workspace_id IS NULL
  AND review.response_id = response.id
  AND response.workspace_id IS NOT NULL;

WITH insight_workspace AS MATERIALIZED (
  SELECT insight.id, MIN(review.workspace_id::TEXT)::UUID AS workspace_id
  FROM public.ai_learning_insights insight
  CROSS JOIN LATERAL jsonb_array_elements_text(
    COALESCE(insight.source_review_ids, '[]'::JSONB)
  ) source_review_id
  JOIN public.ai_attendance_reviews review
    ON review.id = CASE
      WHEN source_review_id ~ '^[0-9]+$' THEN source_review_id::BIGINT
    END
   AND review.workspace_id IS NOT NULL
  WHERE insight.workspace_id IS NULL
  GROUP BY insight.id
)
UPDATE public.ai_learning_insights insight
SET workspace_id = source.workspace_id
FROM insight_workspace source
WHERE insight.id = source.id;

UPDATE public.ai_learning_cases learned_case
SET workspace_id = insight.workspace_id
FROM public.ai_learning_insights insight
WHERE learned_case.workspace_id IS NULL
  AND learned_case.insight_id = insight.id
  AND insight.workspace_id IS NOT NULL;

UPDATE public.ai_agent_instruction_extensions extension
SET workspace_id = insight.workspace_id
FROM public.ai_learning_insights insight
WHERE extension.workspace_id IS NULL
  AND (extension.metadata->>'insight_id') ~ '^[0-9]+$'
  AND CASE
    WHEN (extension.metadata->>'insight_id') ~ '^[0-9]+$'
    THEN (extension.metadata->>'insight_id')::BIGINT
  END = insight.id
  AND insight.workspace_id IS NOT NULL;

DROP INDEX IF EXISTS public.uq_ai_learning_insight_pending_key;
CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_learning_insight_pending_workspace_key
  ON public.ai_learning_insights (
    tenant_id,
    COALESCE(workspace_id, '00000000-0000-0000-0000-000000000000'::UUID),
    insight_key
  )
  WHERE status = 'pending_review';

DROP INDEX IF EXISTS public.uq_ai_learning_cases_key;
CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_learning_cases_workspace_key
  ON public.ai_learning_cases (
    tenant_id,
    COALESCE(workspace_id, '00000000-0000-0000-0000-000000000000'::UUID),
    case_key
  );

CREATE INDEX IF NOT EXISTS idx_ai_attendance_reviews_workspace_created
  ON public.ai_attendance_reviews(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_learning_insights_workspace_status
  ON public.ai_learning_insights(workspace_id, status, importance DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_learning_cases_workspace_status
  ON public.ai_learning_cases(workspace_id, status, importance DESC, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_instruction_extensions_workspace_status
  ON public.ai_agent_instruction_extensions(workspace_id, status, updated_at DESC);

ALTER TABLE public.ai_attendance_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ai_learning_insights ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ai_learning_cases ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ai_agent_instruction_extensions ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.ai_attendance_reviews FROM anon, authenticated;
REVOKE ALL ON TABLE public.ai_learning_insights FROM anon, authenticated;
REVOKE ALL ON TABLE public.ai_learning_cases FROM anon, authenticated;
REVOKE ALL ON TABLE public.ai_agent_instruction_extensions FROM anon, authenticated;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.ai_attendance_reviews TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.ai_learning_insights TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.ai_learning_cases TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.ai_agent_instruction_extensions TO service_role;
GRANT USAGE, SELECT ON SEQUENCE
  public.ai_attendance_reviews_id_seq,
  public.ai_learning_insights_id_seq,
  public.ai_learning_cases_id_seq,
  public.ai_agent_instruction_extensions_id_seq
TO service_role;
