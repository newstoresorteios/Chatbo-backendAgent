CREATE EXTENSION IF NOT EXISTS pg_cron;
CREATE EXTENSION IF NOT EXISTS pg_net WITH SCHEMA extensions;
CREATE SCHEMA IF NOT EXISTS agent_private;
REVOKE ALL ON SCHEMA agent_private FROM PUBLIC,anon,authenticated;
CREATE TABLE agent_private.queue_dispatch_settings(
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 target_url text NOT NULL CHECK(target_url LIKE 'https://%'),
 enabled boolean NOT NULL DEFAULT false,
 min_interval_seconds integer NOT NULL DEFAULT 15 CHECK(min_interval_seconds BETWEEN 10 AND 300),
 last_dispatch_at timestamptz, last_request_id bigint
);
ALTER TABLE agent_private.queue_dispatch_settings ENABLE ROW LEVEL SECURITY;
INSERT INTO agent_private.queue_dispatch_settings(singleton,target_url)
VALUES(true,'https://ns-agent-for-sorteios.vercel.app/api/cron/process-queues');
DO $$ BEGIN
 IF NOT EXISTS(SELECT FROM vault.secrets WHERE name='nsagent_queue_dispatch') THEN
  PERFORM vault.create_secret(encode(extensions.gen_random_bytes(32),'hex'),'nsagent_queue_dispatch','Dedicated queue dispatch authentication');
 END IF;
END $$;
CREATE OR REPLACE FUNCTION agent_private.dispatch_agent_queues() RETURNS bigint
LANGUAGE plpgsql SECURITY INVOKER SET search_path=public,pg_temp AS $$
DECLARE cfg agent_private.queue_dispatch_settings%ROWTYPE; credential text; request_id bigint;
BEGIN
 SELECT * INTO cfg FROM agent_private.queue_dispatch_settings WHERE singleton FOR UPDATE SKIP LOCKED;
 IF NOT FOUND OR NOT cfg.enabled OR cfg.last_dispatch_at > now()-make_interval(secs=>cfg.min_interval_seconds) THEN RETURN NULL; END IF;
 IF NOT EXISTS(SELECT FROM public.ai_inbound_inbox WHERE attempts<max_attempts AND
    (status IN('pending','failed') OR (status='leased' AND lease_expires_at<now())))
    AND NOT EXISTS(SELECT FROM public.ai_outbound_outbox WHERE attempts<max_attempts AND
    (status IN('pending','failed') OR (status='leased' AND lease_expires_at<now()))) THEN RETURN NULL; END IF;
 SELECT decrypted_secret INTO credential FROM vault.decrypted_secrets WHERE name='nsagent_queue_dispatch';
 IF credential IS NULL THEN RAISE EXCEPTION 'queue_dispatch_secret_missing'; END IF;
 SELECT net.http_post(url:=cfg.target_url, body:='{}'::jsonb,
   headers:=jsonb_build_object('Content-Type','application/json','Authorization','Bearer '||credential),
   timeout_milliseconds:=10000) INTO request_id;
 UPDATE agent_private.queue_dispatch_settings SET last_dispatch_at=now(),last_request_id=request_id WHERE singleton;
 RETURN request_id;
END $$;
REVOKE ALL ON FUNCTION agent_private.dispatch_agent_queues() FROM PUBLIC,anon,authenticated;
SELECT cron.schedule('nsagent-durable-queue-dispatch','15 seconds','SELECT agent_private.dispatch_agent_queues();');
-- Dispatcher remains disabled until the authenticated route has been deployed.
