-- Schema base exigido pelo Chatbo (tabelas que as migrations posteriores só alteram).
-- Idempotente: seguro reexecutar.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.usuarios (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT NOT NULL,
  senha_hash TEXT NOT NULL,
  nome TEXT,
  perfil TEXT NOT NULL DEFAULT 'user',
  ativo BOOLEAN NOT NULL DEFAULT TRUE,
  empresa TEXT,
  avatar TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_email_lower
  ON public.usuarios (lower(email));

CREATE TABLE IF NOT EXISTS public.clientes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  mercos_id BIGINT,
  nome TEXT,
  razao_social TEXT,
  cnpj TEXT,
  inscricao_estadual TEXT,
  email TEXT,
  telefone TEXT,
  celular TEXT,
  endereco TEXT,
  numero TEXT,
  complemento TEXT,
  bairro TEXT,
  cidade TEXT,
  estado TEXT,
  cep TEXT,
  ultima_alteracao TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_clientes_mercos_id_lookup
  ON public.clientes(mercos_id)
  WHERE mercos_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.produtos (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  mercos_id BIGINT,
  nome TEXT,
  codigo TEXT,
  unidade TEXT,
  descricao TEXT,
  preco_tabela NUMERIC,
  preco_minimo NUMERIC,
  saldo_estoque NUMERIC,
  ativo BOOLEAN DEFAULT TRUE,
  categoria TEXT,
  currency TEXT DEFAULT 'BRL',
  ultima_alteracao TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_produtos_mercos_id_lookup
  ON public.produtos(mercos_id)
  WHERE mercos_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.pedidos (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  mercos_id BIGINT,
  numero TEXT,
  cliente_mercos_id BIGINT,
  valor_total NUMERIC DEFAULT 0,
  situacao TEXT DEFAULT '2',
  quantidade_itens INTEGER DEFAULT 1,
  data_pedido TIMESTAMPTZ,
  ultima_alteracao TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pedidos_mercos_id_lookup
  ON public.pedidos(mercos_id)
  WHERE mercos_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.leads (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  nome TEXT,
  email TEXT,
  telefone TEXT,
  origem TEXT,
  status TEXT DEFAULT 'new',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
