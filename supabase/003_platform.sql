-- Execute no Supabase: SQL Editor → New query → Run
-- PulseDesk Etapa C: canais, funil, campanhas, chatbot, integrações

CREATE TABLE IF NOT EXISTS public.canais (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  name TEXT NOT NULL,
  connected BOOLEAN NOT NULL DEFAULT true,
  messages_today INT NOT NULL DEFAULT 0,
  phone TEXT,
  last_activity TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.funil_estagios (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  sort_order INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.funil_negocios (
  id TEXT PRIMARY KEY,
  stage_id TEXT NOT NULL REFERENCES public.funil_estagios(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  contact TEXT NOT NULL,
  value NUMERIC(12, 2) NOT NULL DEFAULT 0,
  channel TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.campanhas (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  channel TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft',
  recipients INT NOT NULL DEFAULT 0,
  sent INT NOT NULL DEFAULT 0,
  opened INT NOT NULL DEFAULT 0,
  scheduled_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.chatbot_fluxos (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  channel TEXT NOT NULL,
  active BOOLEAN NOT NULL DEFAULT true,
  triggers INT NOT NULL DEFAULT 0,
  resolved INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.integracoes (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  category TEXT NOT NULL,
  connected BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_funil_negocios_stage_id ON public.funil_negocios(stage_id);
CREATE INDEX IF NOT EXISTS idx_funil_estagios_sort_order ON public.funil_estagios(sort_order);
CREATE INDEX IF NOT EXISTS idx_campanhas_created_at ON public.campanhas(created_at DESC);

ALTER TABLE public.canais ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.funil_estagios ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.funil_negocios ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.campanhas ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.chatbot_fluxos ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.integracoes ENABLE ROW LEVEL SECURITY;
