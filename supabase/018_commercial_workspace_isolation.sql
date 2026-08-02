-- Isolamento comercial incremental por workspace.
-- Registros legados permanecem nullable até um backfill explícito e auditado.
DO $$
BEGIN
  IF to_regclass('public.produtos') IS NOT NULL THEN
    ALTER TABLE public.produtos ADD COLUMN IF NOT EXISTS workspace_id UUID REFERENCES public.workspaces(id);
    CREATE INDEX IF NOT EXISTS idx_produtos_workspace_id ON public.produtos(workspace_id);
  END IF;
  IF to_regclass('public.conversas') IS NOT NULL THEN
    ALTER TABLE public.conversas ADD COLUMN IF NOT EXISTS workspace_id UUID REFERENCES public.workspaces(id);
    CREATE INDEX IF NOT EXISTS idx_conversas_workspace_id ON public.conversas(workspace_id);
  END IF;
  IF to_regclass('public.mensagens') IS NOT NULL THEN
    ALTER TABLE public.mensagens ADD COLUMN IF NOT EXISTS workspace_id UUID REFERENCES public.workspaces(id);
    CREATE INDEX IF NOT EXISTS idx_mensagens_workspace_id ON public.mensagens(workspace_id);
  END IF;
  IF to_regclass('public.clientes') IS NOT NULL THEN
    ALTER TABLE public.clientes ADD COLUMN IF NOT EXISTS workspace_id UUID REFERENCES public.workspaces(id);
    CREATE INDEX IF NOT EXISTS idx_clientes_workspace_id ON public.clientes(workspace_id);
  END IF;
  IF to_regclass('public.pedidos') IS NOT NULL THEN
    ALTER TABLE public.pedidos ADD COLUMN IF NOT EXISTS workspace_id UUID REFERENCES public.workspaces(id);
    CREATE INDEX IF NOT EXISTS idx_pedidos_workspace_id ON public.pedidos(workspace_id);
  END IF;
  IF to_regclass('public.leads') IS NOT NULL THEN
    ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS workspace_id UUID REFERENCES public.workspaces(id);
    CREATE INDEX IF NOT EXISTS idx_leads_workspace_id ON public.leads(workspace_id);
  END IF;
  IF to_regclass('public.campanhas') IS NOT NULL THEN
    ALTER TABLE public.campanhas ADD COLUMN IF NOT EXISTS workspace_id UUID REFERENCES public.workspaces(id);
    CREATE INDEX IF NOT EXISTS idx_campanhas_workspace_id ON public.campanhas(workspace_id);
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS public.workspace_integrations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
  provider TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'disconnected',
  configuration JSONB NOT NULL DEFAULT '{}'::jsonb,
  last_sync_at TIMESTAMPTZ,
  last_sync_status TEXT,
  last_error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT workspace_integrations_provider_check CHECK (provider IN ('mercos')),
  CONSTRAINT workspace_integrations_status_check CHECK (status IN ('connected', 'disconnected', 'error', 'syncing')),
  CONSTRAINT workspace_integrations_unique UNIQUE (workspace_id, provider)
);
CREATE INDEX IF NOT EXISTS idx_workspace_integrations_workspace ON public.workspace_integrations(workspace_id);
ALTER TABLE public.workspace_integrations ENABLE ROW LEVEL SECURITY;
