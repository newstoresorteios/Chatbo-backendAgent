-- Auth tables are backend-only (service_role). If RLS was enabled in the
-- dashboard without policies, login fails with 42501 on refresh_tokens.
-- Disable RLS here; do not expose these tables to the anon client.

ALTER TABLE IF EXISTS public.refresh_tokens DISABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.token_revogados DISABLE ROW LEVEL SECURITY;

GRANT ALL ON TABLE public.refresh_tokens TO service_role;
GRANT ALL ON TABLE public.token_revogados TO service_role;
