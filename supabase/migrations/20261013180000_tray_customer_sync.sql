ALTER TABLE public.clientes ADD COLUMN IF NOT EXISTS tray_id text;
CREATE UNIQUE INDEX IF NOT EXISTS idx_clientes_workspace_tray_id
    ON public.clientes (workspace_id, tray_id);
COMMENT ON COLUMN public.clientes.tray_id IS 'Tray customer ID; independent of Mercos IDs.';
