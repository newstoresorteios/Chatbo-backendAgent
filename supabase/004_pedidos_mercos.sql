-- Execute no Supabase SQL Editor (Etapa 4)
-- Campos extras em pedidos + log de sincronização Mercos

ALTER TABLE public.pedidos
  ADD COLUMN IF NOT EXISTS quantidade_itens INTEGER DEFAULT 1;

ALTER TABLE public.pedidos
  ADD COLUMN IF NOT EXISTS data_pedido TIMESTAMPTZ;

ALTER TABLE public.pedidos
  ADD COLUMN IF NOT EXISTS ultima_alteracao TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_pedidos_situacao ON public.pedidos(situacao);
CREATE INDEX IF NOT EXISTS idx_pedidos_data_pedido ON public.pedidos(data_pedido DESC);
CREATE INDEX IF NOT EXISTS idx_pedidos_cliente_mercos ON public.pedidos(cliente_mercos_id);

CREATE TABLE IF NOT EXISTS public.mercos_sync_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tipo TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'success',
  mensagem TEXT NOT NULL,
  quantidade INTEGER DEFAULT 0,
  resumo JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mercos_sync_logs_created ON public.mercos_sync_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_mercos_sync_logs_tipo ON public.mercos_sync_logs(tipo, created_at DESC);
