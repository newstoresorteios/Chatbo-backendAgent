-- Etapa 11: Segurança JWT — blacklist + refresh tokens
-- Execute no Supabase SQL Editor

CREATE TABLE IF NOT EXISTS public.token_revogados (
  jti TEXT PRIMARY KEY,
  usuario_id TEXT,
  expira_em TIMESTAMPTZ NOT NULL,
  revogado_em TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_token_revogados_expira ON public.token_revogados(expira_em);

CREATE TABLE IF NOT EXISTS public.refresh_tokens (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  usuario_id TEXT NOT NULL,
  token_hash TEXT NOT NULL UNIQUE,
  expira_em TIMESTAMPTZ NOT NULL,
  criado_em TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_usuario ON public.refresh_tokens(usuario_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expira ON public.refresh_tokens(expira_em);
