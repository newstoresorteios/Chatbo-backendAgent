ALTER TABLE public.clientes ADD COLUMN tray_modified_at text;
ALTER TABLE public.clientes ADD COLUMN tray_contacts_pending boolean NOT NULL DEFAULT true;
-- Existing Tray rows were populated through the detail endpoint.
UPDATE public.clientes SET tray_contacts_pending = false WHERE tray_id IS NOT NULL;
CREATE INDEX clientes_tray_pending ON public.clientes(workspace_id, tray_contacts_pending)
WHERE tray_id IS NOT NULL;
CREATE TABLE public.tray_customer_sync_state (
 workspace_id uuid PRIMARY KEY REFERENCES public.workspaces(id) ON DELETE CASCADE,
 phase text NOT NULL DEFAULT 'catalog' CHECK(phase IN ('catalog','contacts','incremental','idle')),
 next_page integer NOT NULL DEFAULT 1 CHECK(next_page > 0),
 scan_date date,
 last_full_at timestamptz,
 last_completed_at timestamptz,
 next_run_at timestamptz NOT NULL DEFAULT now(),
 lease_until timestamptz NOT NULL DEFAULT '1970-01-01',
 lease_token uuid,
 last_error text,
 updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.tray_customer_sync_state ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.tray_customer_sync_state FROM anon, authenticated;
GRANT ALL ON public.tray_customer_sync_state TO service_role;
