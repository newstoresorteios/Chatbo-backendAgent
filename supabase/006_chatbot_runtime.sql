-- Etapa 9: runtime do Robô de Atendimento
-- Execute no Supabase SQL Editor

ALTER TABLE public.conversas
  ADD COLUMN IF NOT EXISTS bot_flow_id TEXT;

ALTER TABLE public.conversas
  ADD COLUMN IF NOT EXISTS bot_activated BOOLEAN DEFAULT false;

CREATE INDEX IF NOT EXISTS idx_conversas_bot_flow_id ON public.conversas(bot_flow_id);
