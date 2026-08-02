-- Etapa 16: contrato real do onboarding empresarial NITRUS
-- Execute no Supabase SQL Editor depois da etapa 15.

CREATE TABLE IF NOT EXISTS public.workspace_channels (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
  channel_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft',
  configuration JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT workspace_channels_type_check CHECK (channel_type IN ('whatsapp', 'webchat')),
  CONSTRAINT workspace_channels_status_check CHECK (status IN ('draft', 'configured', 'active', 'inactive')),
  CONSTRAINT workspace_channels_workspace_type_unique UNIQUE (workspace_id, channel_type)
);

CREATE INDEX IF NOT EXISTS idx_workspace_channels_workspace_id
  ON public.workspace_channels(workspace_id);

CREATE TABLE IF NOT EXISTS public.workspace_onboarding_tests (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
  persona_id UUID NOT NULL REFERENCES public.agent_personas(id) ON DELETE CASCADE,
  status TEXT NOT NULL,
  input_text TEXT NOT NULL,
  output_preview TEXT,
  error_message TEXT,
  completed_at TIMESTAMPTZ,
  created_by TEXT REFERENCES public.usuarios(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT workspace_onboarding_tests_status_check CHECK (status IN ('success', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_workspace_onboarding_tests_workspace_persona
  ON public.workspace_onboarding_tests(workspace_id, persona_id, created_at DESC);
