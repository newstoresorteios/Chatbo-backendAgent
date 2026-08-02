-- Produto vinculado ao pedido (WhatsApp + sync Mercos) para rankings de vendas

ALTER TABLE public.pedidos
  ADD COLUMN IF NOT EXISTS produto_nome TEXT;

ALTER TABLE public.pedidos
  ADD COLUMN IF NOT EXISTS produto_codigo TEXT;

CREATE INDEX IF NOT EXISTS idx_pedidos_produto_nome ON public.pedidos(produto_nome);
