-- Multi-empresa + multi-agente.
-- company_id no produto = workspace_id no banco (alias estável).
-- Cada workspace (empresa) tem um runtime de agente baseado em NSAgent.

CREATE TABLE IF NOT EXISTS public.agent_runtime_types (
  code TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  base_runtime TEXT NOT NULL DEFAULT 'nsagent'
    CHECK (base_runtime IN ('nsagent', 'agentia')),
  description TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO public.agent_runtime_types (code, name, base_runtime, description) VALUES
  ('nsagent', 'NSAgent (base)', 'nsagent', 'Runtime genérico NSAgent para novos agentes'),
  ('nsagent_sorteios', 'NSAgent Sorteios', 'nsagent', 'New Store Sorteios — raffle + Tray + Brevo'),
  ('agentia_vendas', 'AgentIA Vendas', 'agentia', 'xNamai / Mercos vendas — Brevo + PulseDesk')
ON CONFLICT (code) DO NOTHING;

CREATE TABLE IF NOT EXISTS public.workspace_agents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
  agent_type TEXT NOT NULL REFERENCES public.agent_runtime_types(code),
  status TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'inactive', 'provisioning', 'error')),
  display_name TEXT,
  configuration JSONB NOT NULL DEFAULT '{}'::jsonb,
  secrets_ref TEXT,
  webhook_path_key TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT workspace_agents_unique_active UNIQUE (workspace_id)
);

CREATE INDEX IF NOT EXISTS idx_workspace_agents_type
  ON public.workspace_agents(agent_type);
CREATE INDEX IF NOT EXISTS idx_workspace_agents_status
  ON public.workspace_agents(status);

-- Alias explícito: company_id = workspace_id (mesmo valor).
ALTER TABLE public.workspaces
  ADD COLUMN IF NOT EXISTS company_id UUID;

UPDATE public.workspaces
SET company_id = id
WHERE company_id IS NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'workspaces_company_id_matches_id'
  ) THEN
    ALTER TABLE public.workspaces
      ADD CONSTRAINT workspaces_company_id_matches_id
      CHECK (company_id IS NULL OR company_id = id);
  END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_workspaces_company_id
  ON public.workspaces(company_id)
  WHERE company_id IS NOT NULL;

-- Unicidade comercial por empresa (permite mesmo mercos_id em workspaces diferentes).
DO $$
BEGIN
  IF to_regclass('public.clientes') IS NOT NULL THEN
    DROP INDEX IF EXISTS public.idx_clientes_mercos_id;
    CREATE UNIQUE INDEX IF NOT EXISTS idx_clientes_workspace_mercos_id
      ON public.clientes(workspace_id, mercos_id)
      WHERE workspace_id IS NOT NULL AND mercos_id IS NOT NULL;
  END IF;
  IF to_regclass('public.produtos') IS NOT NULL THEN
    CREATE UNIQUE INDEX IF NOT EXISTS idx_produtos_workspace_mercos_id
      ON public.produtos(workspace_id, mercos_id)
      WHERE workspace_id IS NOT NULL AND mercos_id IS NOT NULL;
  END IF;
  IF to_regclass('public.pedidos') IS NOT NULL THEN
    DROP INDEX IF EXISTS public.idx_pedidos_mercos_id;
    CREATE UNIQUE INDEX IF NOT EXISTS idx_pedidos_workspace_mercos_id
      ON public.pedidos(workspace_id, mercos_id)
      WHERE workspace_id IS NOT NULL AND mercos_id IS NOT NULL;
  END IF;
END $$;

-- Colunas de isolamento para tabelas do runtime NSAgent (quando já existirem).
DO $$
DECLARE
  t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'ai_inbound_messages',
    'ai_agent_responses',
    'ai_user_preferences',
    'ai_remarketing_contacts',
    'ai_conversation_statuses',
    'ai_remarketing_attempts',
    'ai_customer_identity_links',
    'ai_customer_commerce_sessions',
    'ai_agent_persona_versions',
    'ai_prompt_compilations',
    'ai_agent_instruction_extensions',
    'ai_contact_memories',
    'ai_conversation_summaries',
    'ai_memory_proposals',
    'ai_pix_payments',
    'pagamentos_pix'
  ]
  LOOP
    IF to_regclass('public.' || t) IS NOT NULL THEN
      EXECUTE format(
        'ALTER TABLE public.%I ADD COLUMN IF NOT EXISTS workspace_id UUID REFERENCES public.workspaces(id)',
        t
      );
      EXECUTE format(
        'CREATE INDEX IF NOT EXISTS idx_%s_workspace_id ON public.%I(workspace_id)',
        t, t
      );
    END IF;
  END LOOP;
END $$;

-- Seed: workspaces sem agente recebem nsagent base (ajuste manual depois).
INSERT INTO public.workspace_agents (workspace_id, agent_type, status, display_name)
SELECT w.id, 'nsagent', 'active', COALESCE(w.brand_name, w.name)
FROM public.workspaces w
WHERE w.status = 'active'
  AND NOT EXISTS (
    SELECT 1 FROM public.workspace_agents wa WHERE wa.workspace_id = w.id
  );
