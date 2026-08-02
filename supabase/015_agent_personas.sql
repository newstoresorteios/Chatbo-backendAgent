-- Etapa 15: personas do agente NITRUS por workspace
-- Execute no Supabase SQL Editor depois da fundacao de workspaces.

CREATE TABLE IF NOT EXISTS public.agent_personas (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
  name TEXT,
  role TEXT,
  segment TEXT,
  language TEXT NOT NULL DEFAULT 'pt-BR',
  tone TEXT,
  tone_details TEXT,
  greeting TEXT,
  introduction TEXT,
  customer_address_style TEXT,
  closing_message TEXT,
  target_audience TEXT,
  customer_profile TEXT,
  sales_goals JSONB NOT NULL DEFAULT '[]'::jsonb,
  qualification_rules JSONB NOT NULL DEFAULT '[]'::jsonb,
  opportunity_criteria JSONB NOT NULL DEFAULT '[]'::jsonb,
  human_handoff_criteria JSONB NOT NULL DEFAULT '[]'::jsonb,
  objection_handling JSONB NOT NULL DEFAULT '{}'::jsonb,
  upsell_rules JSONB NOT NULL DEFAULT '[]'::jsonb,
  recommendation_rules JSONB NOT NULL DEFAULT '[]'::jsonb,
  escalation_rules JSONB NOT NULL DEFAULT '[]'::jsonb,
  restrictions JSONB NOT NULL DEFAULT '[]'::jsonb,
  examples JSONB NOT NULL DEFAULT '[]'::jsonb,
  status TEXT NOT NULL DEFAULT 'draft',
  version INTEGER NOT NULL DEFAULT 1,
  created_by TEXT REFERENCES public.usuarios(id) ON DELETE SET NULL,
  updated_by TEXT REFERENCES public.usuarios(id) ON DELETE SET NULL,
  activated_by TEXT REFERENCES public.usuarios(id) ON DELETE SET NULL,
  activated_at TIMESTAMPTZ,
  deactivated_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  CONSTRAINT agent_personas_status_check CHECK (status IN ('draft', 'active', 'inactive')),
  CONSTRAINT agent_personas_version_check CHECK (version > 0)
);

CREATE INDEX IF NOT EXISTS idx_agent_personas_workspace_id
  ON public.agent_personas(workspace_id);

CREATE INDEX IF NOT EXISTS idx_agent_personas_workspace_status
  ON public.agent_personas(workspace_id, status);

CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_personas_one_active_workspace
  ON public.agent_personas(workspace_id)
  WHERE status = 'active';

CREATE TABLE IF NOT EXISTS public.agent_persona_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  persona_id UUID NOT NULL REFERENCES public.agent_personas(id) ON DELETE CASCADE,
  workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
  version INTEGER NOT NULL,
  snapshot JSONB NOT NULL,
  change_type TEXT NOT NULL,
  created_by TEXT REFERENCES public.usuarios(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  CONSTRAINT agent_persona_versions_change_type_check CHECK (
    change_type IN ('created', 'updated', 'activated', 'deactivated')
  ),
  CONSTRAINT agent_persona_versions_version_check CHECK (version > 0),
  CONSTRAINT agent_persona_versions_persona_version_unique UNIQUE (persona_id, version)
);

CREATE INDEX IF NOT EXISTS idx_agent_persona_versions_persona_version
  ON public.agent_persona_versions(persona_id, version DESC);

CREATE INDEX IF NOT EXISTS idx_agent_persona_versions_workspace_id
  ON public.agent_persona_versions(workspace_id);
