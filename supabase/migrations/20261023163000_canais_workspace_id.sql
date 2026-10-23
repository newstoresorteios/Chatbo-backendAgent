-- YCloud pilot: channels are claimed by one workspace; the connect flow and the
-- inbound/status SQL functions filter canais by workspace_id.
ALTER TABLE public.canais
  ADD COLUMN IF NOT EXISTS workspace_id uuid REFERENCES public.workspaces(id);

CREATE INDEX IF NOT EXISTS idx_canais_workspace_id ON public.canais (workspace_id);

NOTIFY pgrst, 'reload schema';
