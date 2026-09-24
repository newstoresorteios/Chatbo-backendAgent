-- Server-only subscriber. No new grants or RLS policies for browser roles.
DO $$
DECLARE target text;
BEGIN
  FOREACH target IN ARRAY ARRAY['ai_inbound_messages', 'ai_agent_responses', 'conversas', 'mensagens']
  LOOP
    IF NOT EXISTS (
      SELECT 1 FROM pg_publication_tables
      WHERE pubname = 'supabase_realtime' AND schemaname = 'public' AND tablename = target
    ) THEN
      EXECUTE format('ALTER PUBLICATION supabase_realtime ADD TABLE public.%I', target);
    END IF;
  END LOOP;
END $$;
