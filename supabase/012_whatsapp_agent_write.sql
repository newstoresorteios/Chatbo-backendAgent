-- Permite o agente WhatsApp gravar clientes e pedidos no PulseDesk (Supabase)
-- Execute no SQL Editor do Supabase se inserts falharem por permissão.
-- Use SUPABASE_SERVICE_ROLE key no agent (Render), não a anon key.

-- Garante unique em mercos_id (upsert do agent)
CREATE UNIQUE INDEX IF NOT EXISTS idx_clientes_mercos_id ON public.clientes(mercos_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_pedidos_mercos_id ON public.pedidos(mercos_id);

-- Políticas permissivas para service_role / authenticated (ajuste conforme seu auth)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE tablename = 'clientes' AND policyname = 'agent_write_clientes'
  ) THEN
    CREATE POLICY agent_write_clientes ON public.clientes
      FOR ALL USING (true) WITH CHECK (true);
  END IF;
EXCEPTION WHEN undefined_table THEN
  RAISE NOTICE 'Tabela clientes não existe ainda';
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE tablename = 'pedidos' AND policyname = 'agent_write_pedidos'
  ) THEN
    CREATE POLICY agent_write_pedidos ON public.pedidos
      FOR ALL USING (true) WITH CHECK (true);
  END IF;
EXCEPTION WHEN undefined_table THEN
  RAISE NOTICE 'Tabela pedidos não existe ainda';
END $$;
