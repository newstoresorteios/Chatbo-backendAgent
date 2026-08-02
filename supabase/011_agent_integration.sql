-- Integração agente de vendas + PulseDesk
-- Execute no Supabase SQL Editor

-- Histórico interno do agente (não conflita com conversas/mensagens do PulseDesk)
CREATE TABLE IF NOT EXISTS public.agent_clientes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  telefone TEXT NOT NULL UNIQUE,
  nome TEXT DEFAULT '',
  historico JSONB DEFAULT '[]'::jsonb,
  openai_thread_id TEXT,
  mercos_cliente_id BIGINT,
  criado_em TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.agent_historico (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cliente_id UUID NOT NULL REFERENCES public.agent_clientes(id) ON DELETE CASCADE,
  tipo TEXT NOT NULL,
  mensagem TEXT NOT NULL,
  criado_em TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_historico_cliente
  ON public.agent_historico(cliente_id, criado_em);

CREATE INDEX IF NOT EXISTS idx_agent_clientes_telefone
  ON public.agent_clientes(telefone);
