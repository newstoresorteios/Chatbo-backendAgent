-- Etapa 10: Configurações reais
-- Execute no Supabase SQL Editor

CREATE TABLE IF NOT EXISTS public.empresa_config (
  id TEXT PRIMARY KEY DEFAULT 'default',
  nome TEXT NOT NULL DEFAULT 'PulseDesk',
  cnpj TEXT,
  email TEXT,
  telefone TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO public.empresa_config (id, nome)
VALUES ('default', 'PulseDesk')
ON CONFLICT (id) DO NOTHING;

ALTER TABLE public.usuarios
  ADD COLUMN IF NOT EXISTS preferencias JSONB DEFAULT '{}'::jsonb;
