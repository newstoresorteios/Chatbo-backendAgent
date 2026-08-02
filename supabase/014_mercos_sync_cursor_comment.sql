-- Opcional: documenta o cursor de sync incremental no resumo JSONB.
-- NÃO é obrigatório executar: o código já grava cursor_ultima_alteracao
-- em mercos_sync_logs.resumo (coluna JSONB existente desde 004_pedidos_mercos.sql).
--
-- Logs antigos sem o campo caem no fallback created_at.

COMMENT ON COLUMN public.mercos_sync_logs.resumo IS
  'Metadados do sync; pode incluir cursor_ultima_alteracao (timestamp Mercos) para alterado_apos.';
