-- Etapa 22: fonte Tray (TRAYadaptor) + snapshots BI comerciais por workspace

-- Amplia providers de integração (mercos | tray)
DO $$
DECLARE
  constraint_name text;
BEGIN
  FOR constraint_name IN
    SELECT con.conname
    FROM pg_constraint con
    WHERE con.conrelid = 'public.workspace_integrations'::regclass
      AND con.contype = 'c'
      AND pg_get_constraintdef(con.oid) ILIKE '%provider%'
  LOOP
    EXECUTE format('ALTER TABLE public.workspace_integrations DROP CONSTRAINT %I', constraint_name);
  END LOOP;

  ALTER TABLE public.workspace_integrations
    ADD CONSTRAINT workspace_integrations_provider_check
    CHECK (provider IN ('mercos', 'tray'));
END $$;

CREATE TABLE IF NOT EXISTS public.commercial_bi_snapshots (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
  period_days INTEGER NOT NULL DEFAULT 30,
  status TEXT NOT NULL DEFAULT 'running',
  kpis JSONB NOT NULL DEFAULT '{}'::jsonb,
  entities JSONB NOT NULL DEFAULT '{}'::jsonb,
  insights JSONB NOT NULL DEFAULT '{}'::jsonb,
  attribution JSONB NOT NULL DEFAULT '{}'::jsonb,
  source_meta JSONB NOT NULL DEFAULT '{}'::jsonb,
  error_message TEXT,
  created_by UUID REFERENCES public.usuarios(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at TIMESTAMPTZ,
  CONSTRAINT commercial_bi_snapshots_status_check CHECK (
    status IN ('running', 'ready', 'failed')
  ),
  CONSTRAINT commercial_bi_snapshots_period_check CHECK (period_days > 0)
);

CREATE INDEX IF NOT EXISTS idx_commercial_bi_snapshots_workspace_created
  ON public.commercial_bi_snapshots(workspace_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_commercial_bi_snapshots_workspace_ready
  ON public.commercial_bi_snapshots(workspace_id, created_at DESC)
  WHERE status = 'ready';

ALTER TABLE public.commercial_bi_snapshots ENABLE ROW LEVEL SECURITY;
