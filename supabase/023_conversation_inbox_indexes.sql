-- Central de Conversao: indexes aligned with workspace-scoped cursor pagination.
-- Safe to run more than once.

CREATE INDEX IF NOT EXISTS idx_conversas_workspace_last_message
  ON public.conversas (workspace_id, last_message_at DESC);

CREATE INDEX IF NOT EXISTS idx_mensagens_conversa_created
  ON public.mensagens (conversa_id, created_at DESC);

