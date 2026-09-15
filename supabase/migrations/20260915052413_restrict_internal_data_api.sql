-- ChatBo uses its own JWT and workspace authorization in the backend.
-- No browser accesses these internal tables directly. service_role/postgres remain.
DO $$
DECLARE item record;
BEGIN
  FOR item IN SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
              WHERE n.nspname='public' AND c.relkind IN ('r','p')
  LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', item.relname);
  END LOOP;
END $$;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated, PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated, PUBLIC;
DROP POLICY IF EXISTS agent_write_clientes ON public.clientes;
DROP POLICY IF EXISTS agent_write_pedidos ON public.pedidos;
-- Keep application RPCs internal, including SECURITY DEFINER entry points.
DO $$
DECLARE item record;
BEGIN
  FOR item IN SELECT p.oid::regprocedure AS signature FROM pg_proc p
              JOIN pg_namespace n ON n.oid=p.pronamespace
              WHERE n.nspname='public'
                AND NOT EXISTS (SELECT FROM pg_depend d WHERE d.objid=p.oid AND d.deptype='e')
  LOOP
    EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM anon, authenticated, PUBLIC', item.signature);
    EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO service_role', item.signature);
    EXECUTE format('ALTER FUNCTION %s SET search_path = public, pg_temp', item.signature);
  END LOOP;
END $$;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON TABLES FROM anon, authenticated, PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON SEQUENCES FROM anon, authenticated, PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM anon, authenticated, PUBLIC;
NOTIFY pgrst, 'reload schema';
