-- Etapa 21: anexos de conhecimento da persona (usados pelo agente no activate)
-- Execute no Supabase SQL Editor. Crie também o bucket Storage "persona-knowledge" (privado)
-- se o INSERT abaixo não tiver permissão no seu projeto.

CREATE TABLE IF NOT EXISTS public.agent_persona_attachments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  persona_id UUID NOT NULL REFERENCES public.agent_personas(id) ON DELETE CASCADE,
  workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
  filename TEXT NOT NULL,
  content_type TEXT,
  byte_size INTEGER NOT NULL DEFAULT 0,
  storage_path TEXT NOT NULL,
  extracted_text TEXT,
  status TEXT NOT NULL DEFAULT 'uploaded',
  error_message TEXT,
  created_by UUID REFERENCES public.usuarios(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  CONSTRAINT agent_persona_attachments_status_check CHECK (
    status IN ('uploaded', 'processed', 'failed')
  ),
  CONSTRAINT agent_persona_attachments_size_check CHECK (byte_size >= 0)
);

CREATE INDEX IF NOT EXISTS idx_agent_persona_attachments_persona
  ON public.agent_persona_attachments(persona_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_agent_persona_attachments_workspace
  ON public.agent_persona_attachments(workspace_id);

-- Bucket privado para documentos da persona (ignore se já existir / sem permissão)
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'persona-knowledge',
  'persona-knowledge',
  false,
  5242880,
  ARRAY[
    'text/plain',
    'text/markdown',
    'text/csv',
    'application/json',
    'application/pdf',
    'application/octet-stream'
  ]
)
ON CONFLICT (id) DO NOTHING;
