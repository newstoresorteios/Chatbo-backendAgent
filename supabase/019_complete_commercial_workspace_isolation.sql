-- Completa e valida o isolamento comercial introduzido pela migration 018.
-- Esta migration nao executa backfill automaticamente.

DO $$
DECLARE
  required_table TEXT;
  required_tables CONSTANT TEXT[] := ARRAY[
    'produtos',
    'clientes',
    'leads',
    'workspace_integrations'
  ];
BEGIN
  IF to_regclass('public.workspaces') IS NULL THEN
    RAISE EXCEPTION 'Pre-condicao ausente: public.workspaces nao existe';
  END IF;

  FOREACH required_table IN ARRAY required_tables LOOP
    IF to_regclass(format('public.%I', required_table)) IS NULL THEN
      RAISE EXCEPTION 'Pre-condicao ausente: public.% existe', required_table;
    END IF;
  END LOOP;

  FOREACH required_table IN ARRAY ARRAY['produtos', 'clientes', 'leads']::TEXT[] LOOP
    IF NOT EXISTS (
      SELECT 1
      FROM pg_attribute attribute
      WHERE attribute.attrelid = format('public.%I', required_table)::regclass
        AND attribute.attname = 'workspace_id'
        AND attribute.atttypid = 'uuid'::regtype
        AND NOT attribute.attisdropped
    ) THEN
      RAISE EXCEPTION 'Pre-condicao ausente: public.%.workspace_id deve ser UUID', required_table;
    END IF;
  END LOOP;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_attribute attribute
    WHERE attribute.attrelid = 'public.workspace_integrations'::regclass
      AND attribute.attname = 'workspace_id'
      AND attribute.atttypid = 'uuid'::regtype
      AND NOT attribute.attisdropped
  ) THEN
    RAISE EXCEPTION 'Pre-condicao ausente: public.workspace_integrations.workspace_id deve ser UUID';
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_produtos_workspace_id
  ON public.produtos(workspace_id);

CREATE INDEX IF NOT EXISTS idx_clientes_workspace_id
  ON public.clientes(workspace_id);

CREATE INDEX IF NOT EXISTS idx_leads_workspace_id
  ON public.leads(workspace_id);

CREATE INDEX IF NOT EXISTS idx_workspace_integrations_workspace
  ON public.workspace_integrations(workspace_id);

DO $$
DECLARE
  table_name TEXT;
  workspace_attribute SMALLINT;
BEGIN
  FOREACH table_name IN ARRAY ARRAY['produtos', 'clientes', 'leads']::TEXT[] LOOP
    SELECT attribute.attnum
      INTO workspace_attribute
    FROM pg_attribute attribute
    WHERE attribute.attrelid = format('public.%I', table_name)::regclass
      AND attribute.attname = 'workspace_id'
      AND NOT attribute.attisdropped;

    IF NOT EXISTS (
      SELECT 1
      FROM pg_constraint constraint_row
      WHERE constraint_row.conrelid = format('public.%I', table_name)::regclass
        AND constraint_row.contype = 'f'
        AND constraint_row.confrelid = 'public.workspaces'::regclass
        AND constraint_row.conkey = ARRAY[workspace_attribute]::smallint[]
    ) THEN
      EXECUTE format(
        'ALTER TABLE public.%I ADD CONSTRAINT %I FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id)',
        table_name,
        table_name || '_workspace_id_fkey'
      );
    END IF;
  END LOOP;

  SELECT attribute.attnum
    INTO workspace_attribute
  FROM pg_attribute attribute
  WHERE attribute.attrelid = 'public.workspace_integrations'::regclass
    AND attribute.attname = 'workspace_id'
    AND NOT attribute.attisdropped;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint constraint_row
    WHERE constraint_row.conrelid = 'public.workspace_integrations'::regclass
      AND constraint_row.contype = 'f'
      AND constraint_row.confrelid = 'public.workspaces'::regclass
      AND constraint_row.conkey = ARRAY[workspace_attribute]::smallint[]
  ) THEN
    ALTER TABLE public.workspace_integrations
      ADD CONSTRAINT workspace_integrations_workspace_id_fkey
      FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id)
      ON DELETE CASCADE;
  END IF;
END $$;

CREATE OR REPLACE FUNCTION public.backfill_legacy_commercial_workspace(
  target_workspace_id UUID,
  expected_products INTEGER,
  expected_customers INTEGER,
  expected_leads INTEGER
)
RETURNS TABLE (
  products_updated INTEGER,
  customers_updated INTEGER,
  leads_updated INTEGER
)
LANGUAGE plpgsql
AS $$
DECLARE
  actual_products INTEGER;
  actual_customers INTEGER;
  actual_leads INTEGER;
BEGIN
  IF target_workspace_id IS NULL THEN
    RAISE EXCEPTION 'target_workspace_id e obrigatorio';
  END IF;

  IF expected_products < 0 OR expected_customers < 0 OR expected_leads < 0 THEN
    RAISE EXCEPTION 'As contagens esperadas nao podem ser negativas';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM public.workspaces WHERE id = target_workspace_id
  ) THEN
    RAISE EXCEPTION 'Workspace de destino nao existe: %', target_workspace_id;
  END IF;

  LOCK TABLE public.produtos, public.clientes, public.leads IN SHARE ROW EXCLUSIVE MODE;

  SELECT COUNT(*) INTO actual_products
  FROM public.produtos
  WHERE workspace_id IS NULL;

  SELECT COUNT(*) INTO actual_customers
  FROM public.clientes
  WHERE workspace_id IS NULL;

  SELECT COUNT(*) INTO actual_leads
  FROM public.leads
  WHERE workspace_id IS NULL;

  IF actual_products <> expected_products THEN
    RAISE EXCEPTION 'Contagem de produtos divergente: esperado %, encontrado %', expected_products, actual_products;
  END IF;

  IF actual_customers <> expected_customers THEN
    RAISE EXCEPTION 'Contagem de clientes divergente: esperado %, encontrado %', expected_customers, actual_customers;
  END IF;

  IF actual_leads <> expected_leads THEN
    RAISE EXCEPTION 'Contagem de leads divergente: esperado %, encontrado %', expected_leads, actual_leads;
  END IF;

  UPDATE public.produtos
  SET workspace_id = target_workspace_id
  WHERE workspace_id IS NULL;
  GET DIAGNOSTICS products_updated = ROW_COUNT;

  UPDATE public.clientes
  SET workspace_id = target_workspace_id
  WHERE workspace_id IS NULL;
  GET DIAGNOSTICS customers_updated = ROW_COUNT;

  UPDATE public.leads
  SET workspace_id = target_workspace_id
  WHERE workspace_id IS NULL;
  GET DIAGNOSTICS leads_updated = ROW_COUNT;

  RETURN NEXT;
END;
$$;

COMMENT ON FUNCTION public.backfill_legacy_commercial_workspace(UUID, INTEGER, INTEGER, INTEGER)
IS 'Backfill administrativo explicito e protegido por contagem; nunca escolher workspace automaticamente.';

NOTIFY pgrst, 'reload schema';
