-- F16: NS-db (mgwvavsjxzwflibcjzhd) only. This is NOT the NSAgent database.
-- Reviewed 2026-10-01: 55 public tables owned by postgres, one view; browser
-- business data goes through the server API. Active payments/draws SQL sessions
-- use postgres/Supavisor. postgres and service_role both have BYPASSRLS.
-- Keep the existing server roles; no invented customer auth.uid() policies.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

DO $$
BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='postgres' AND rolbypassrls)
    OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='service_role' AND rolbypassrls)
 THEN RAISE EXCEPTION 'legacy_server_roles_require_review'; END IF;
 IF EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m')
              AND pg_get_userbyid(c.relowner)<>'postgres')
 THEN RAISE EXCEPTION 'legacy_object_owner_changed_review_required'; END IF;
END $$;

DO $$ DECLARE item record; BEGIN
 FOR item IN SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='public' AND c.relkind IN ('r','p')
 LOOP EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',item.relname); END LOOP;
END $$;

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC,anon,authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC,anon,authenticated;
-- Server APIs retain their existing access, including sequences and views.
GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO service_role;
GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO service_role;

DO $$ DECLARE item record; BEGIN
 FOR item IN SELECT p.oid::regprocedure signature FROM pg_proc p
             JOIN pg_namespace n ON n.oid=p.pronamespace
             WHERE n.nspname='public'
               AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid=p.oid AND d.deptype='e')
 LOOP
  EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC,anon,authenticated',item.signature);
  EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO service_role',item.signature);
 END LOOP;
END $$;

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON TABLES FROM PUBLIC,anon,authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON SEQUENCES FROM PUBLIC,anon,authenticated;
-- Function EXECUTE has a global PUBLIC default; a schema-only REVOKE cannot remove it.
ALTER DEFAULT PRIVILEGES FOR ROLE postgres REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC,anon,authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT SELECT,INSERT,UPDATE,DELETE ON TABLES TO service_role;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT USAGE,SELECT ON SEQUENCES TO service_role;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO service_role;

NOTIFY pgrst,'reload schema';
COMMIT;
