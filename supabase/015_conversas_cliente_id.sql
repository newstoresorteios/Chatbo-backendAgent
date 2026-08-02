-- ============================================================
-- 015_conversas_cliente_id.sql
-- Relacionamento seguro conversas → clientes via UUID
--
-- Objetivo:
--   adicionar conversas.cliente_id (uuid) → clientes.id
--   sem remover nem alterar cliente_mercos_id (text)
--
-- Seguro / compatível:
--   - coluna nova nullable
--   - cliente_mercos_id permanece
--   - FK só depois do backfill
--   - ON DELETE SET NULL (não apaga conversa se cliente sumir)
--
-- NÃO aplicar automaticamente — revisar e rodar no SQL Editor.
-- ============================================================

-- ---------- UP ----------

-- 1) Coluna nova (não remove nada)
ALTER TABLE public.conversas
  ADD COLUMN IF NOT EXISTS cliente_id uuid;

COMMENT ON COLUMN public.conversas.cliente_id IS
  'FK opcional para public.clientes.id. Compatível com cliente_mercos_id (legado Mercos).';

-- 2) Backfill: liga pelo mercos_id quando cliente_mercos_id for numérico
UPDATE public.conversas AS c
SET cliente_id = cl.id
FROM public.clientes AS cl
WHERE c.cliente_id IS NULL
  AND c.cliente_mercos_id IS NOT NULL
  AND btrim(c.cliente_mercos_id) <> ''
  AND c.cliente_mercos_id ~ '^[0-9]+$'
  AND cl.mercos_id IS NOT NULL
  AND cl.mercos_id = (btrim(c.cliente_mercos_id))::bigint;

-- 3) Índice para joins / filtros
CREATE INDEX IF NOT EXISTS idx_conversas_cliente_id
  ON public.conversas (cliente_id)
  WHERE cliente_id IS NOT NULL;

-- 4) Foreign key somente após o preenchimento
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'conversas_cliente_id_fkey'
      AND conrelid = 'public.conversas'::regclass
  ) THEN
    ALTER TABLE public.conversas
      ADD CONSTRAINT conversas_cliente_id_fkey
      FOREIGN KEY (cliente_id)
      REFERENCES public.clientes (id)
      ON DELETE SET NULL;
  END IF;
END $$;

-- Diagnóstico opcional (descomente para inspecionar):
-- SELECT
--   count(*) AS total,
--   count(cliente_mercos_id) FILTER (WHERE btrim(coalesce(cliente_mercos_id, '')) <> '') AS com_mercos_text,
--   count(cliente_id) AS com_cliente_id,
--   count(*) FILTER (
--     WHERE btrim(coalesce(cliente_mercos_id, '')) ~ '^[0-9]+$'
--       AND cliente_id IS NULL
--   ) AS mercos_sem_match
-- FROM public.conversas;


-- ============================================================
-- DOWN (reversão manual — rodar só se precisar desfazer)
-- Não remove cliente_mercos_id. Remove apenas a coluna nova + FK.
-- ============================================================
--
-- ALTER TABLE public.conversas DROP CONSTRAINT IF EXISTS conversas_cliente_id_fkey;
-- DROP INDEX IF EXISTS public.idx_conversas_cliente_id;
-- ALTER TABLE public.conversas DROP COLUMN IF EXISTS cliente_id;
