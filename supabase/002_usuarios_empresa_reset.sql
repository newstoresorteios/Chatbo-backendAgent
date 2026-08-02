-- Execute no Supabase SQL Editor (Etapa 3)
-- Campos empresa + recuperação de senha na tabela usuarios

ALTER TABLE public.usuarios
  ADD COLUMN IF NOT EXISTS empresa TEXT;

ALTER TABLE public.usuarios
  ADD COLUMN IF NOT EXISTS reset_token TEXT;

ALTER TABLE public.usuarios
  ADD COLUMN IF NOT EXISTS reset_token_expires TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_usuarios_reset_token ON public.usuarios(reset_token);
