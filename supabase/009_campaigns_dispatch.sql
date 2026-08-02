-- PulseDesk Etapa 14: disparo real de campanhas WhatsApp
ALTER TABLE public.campanhas
  ADD COLUMN IF NOT EXISTS message TEXT,
  ADD COLUMN IF NOT EXISTS failed INT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS dispatched_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS last_error TEXT;
