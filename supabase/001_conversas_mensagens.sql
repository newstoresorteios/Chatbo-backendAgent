-- Execute no Supabase: SQL Editor → New query → Run
-- PulseDesk: conversas e mensagens

CREATE TABLE IF NOT EXISTS public.conversas (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cliente_mercos_id TEXT,
  customer_name TEXT NOT NULL,
  customer_avatar TEXT,
  last_message TEXT DEFAULT '',
  last_message_at TIMESTAMPTZ DEFAULT NOW(),
  status TEXT NOT NULL DEFAULT 'active',
  unread_count INT NOT NULL DEFAULT 0,
  channel TEXT NOT NULL DEFAULT 'whatsapp',
  department TEXT,
  protocol TEXT,
  assigned_to TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.mensagens (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversa_id UUID NOT NULL REFERENCES public.conversas(id) ON DELETE CASCADE,
  content TEXT NOT NULL,
  sender TEXT NOT NULL DEFAULT 'agent',
  status TEXT NOT NULL DEFAULT 'sent',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mensagens_conversa_id ON public.mensagens(conversa_id);
CREATE INDEX IF NOT EXISTS idx_conversas_last_message_at ON public.conversas(last_message_at DESC);

ALTER TABLE public.conversas ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.mensagens ENABLE ROW LEVEL SECURITY;
