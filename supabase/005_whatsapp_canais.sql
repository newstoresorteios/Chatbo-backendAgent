-- Execute no Supabase SQL Editor (Etapa 5)
-- WhatsApp / canais reais — credenciais, thread IDs, deduplicação

ALTER TABLE public.canais
  ADD COLUMN IF NOT EXISTS provider TEXT DEFAULT 'manual';

ALTER TABLE public.canais
  ADD COLUMN IF NOT EXISTS provider_status TEXT DEFAULT 'pending';

ALTER TABLE public.canais
  ADD COLUMN IF NOT EXISTS phone_number_id TEXT;

ALTER TABLE public.canais
  ADD COLUMN IF NOT EXISTS waba_id TEXT;

ALTER TABLE public.canais
  ADD COLUMN IF NOT EXISTS access_token TEXT;

ALTER TABLE public.canais
  ADD COLUMN IF NOT EXISTS display_phone TEXT;

ALTER TABLE public.canais
  ADD COLUMN IF NOT EXISTS config JSONB DEFAULT '{}'::jsonb;

ALTER TABLE public.conversas
  ADD COLUMN IF NOT EXISTS canal_id TEXT;

ALTER TABLE public.conversas
  ADD COLUMN IF NOT EXISTS external_thread_id TEXT;

ALTER TABLE public.conversas
  ADD COLUMN IF NOT EXISTS contact_phone TEXT;

ALTER TABLE public.mensagens
  ADD COLUMN IF NOT EXISTS external_id TEXT;

ALTER TABLE public.mensagens
  ADD COLUMN IF NOT EXISTS direction TEXT DEFAULT 'outbound';

ALTER TABLE public.mensagens
  ADD COLUMN IF NOT EXISTS provider_status TEXT;

CREATE INDEX IF NOT EXISTS idx_conversas_canal_thread
  ON public.conversas(canal_id, external_thread_id);

CREATE INDEX IF NOT EXISTS idx_mensagens_external_id
  ON public.mensagens(external_id);

CREATE INDEX IF NOT EXISTS idx_canais_phone_number_id
  ON public.canais(phone_number_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_mensagens_external_id_unique
  ON public.mensagens(external_id)
  WHERE external_id IS NOT NULL;
