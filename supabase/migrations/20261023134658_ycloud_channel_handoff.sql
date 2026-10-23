-- Pilot YCloud number: keep customer-service window and channel identity scoped.
ALTER TABLE public.conversas
  ADD COLUMN IF NOT EXISTS last_customer_message_at timestamptz;

ALTER TABLE public.conversas
  ADD COLUMN IF NOT EXISTS provider text;

CREATE UNIQUE INDEX IF NOT EXISTS idx_canais_ycloud_waba_phone_unique
  ON public.canais (waba_id, display_phone)
  WHERE provider = 'ycloud';

-- Insert the message, update the unread count and advance the 24-hour window
-- in one transaction. A unique provider message ID makes retries harmless.
CREATE OR REPLACE FUNCTION public.ycloud_ingest_inbound(
    p_channel_id text, p_workspace_id uuid, p_external_id text,
    p_customer text, p_customer_name text, p_content text,
    p_sent_at timestamptz, p_human_request boolean
) RETURNS jsonb
LANGUAGE plpgsql
SET search_path = public
AS $$
DECLARE
    v_conversation public.conversas%ROWTYPE;
    v_message_id uuid;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM public.canais
        WHERE id = p_channel_id AND workspace_id = p_workspace_id
          AND provider = 'ycloud' AND connected = true
    ) THEN
        RAISE EXCEPTION 'YCloud channel unavailable';
    END IF;

    SELECT * INTO v_conversation FROM public.conversas
    WHERE workspace_id = p_workspace_id AND channel = 'whatsapp'
      AND canal_id = p_channel_id AND external_thread_id = p_customer
      AND merged_into IS NULL
    LIMIT 1 FOR UPDATE;
    IF NOT FOUND THEN
        BEGIN
            INSERT INTO public.conversas (
                workspace_id, canal_id, external_thread_id, contact_phone,
                customer_name, channel, provider, status, bot_activated,
                unread_count, last_message, last_message_at, last_customer_message_at
            ) VALUES (
                p_workspace_id, p_channel_id, p_customer, p_customer,
                p_customer_name, 'whatsapp', 'ycloud', 'active', true,
                0, '', p_sent_at, p_sent_at
            ) RETURNING * INTO v_conversation;
        EXCEPTION WHEN unique_violation THEN
            SELECT * INTO v_conversation FROM public.conversas
            WHERE workspace_id = p_workspace_id AND channel = 'whatsapp'
              AND canal_id = p_channel_id AND external_thread_id = p_customer
              AND merged_into IS NULL
            LIMIT 1 FOR UPDATE;
            IF NOT FOUND THEN RAISE; END IF;
        END;
    END IF;

    INSERT INTO public.mensagens (
        conversa_id, workspace_id, content, sender, direction,
        status, provider_status, external_id, created_at
    ) VALUES (
        v_conversation.id, p_workspace_id, p_content, 'customer', 'inbound',
        'delivered', 'received', p_external_id, p_sent_at
    ) ON CONFLICT (external_id) WHERE external_id IS NOT NULL DO NOTHING
      RETURNING id INTO v_message_id;
    IF v_message_id IS NULL THEN
        RETURN jsonb_build_object('inserted', false);
    END IF;

    UPDATE public.conversas SET
        unread_count = coalesce(unread_count, 0) + 1,
        last_customer_message_at = greatest(coalesce(last_customer_message_at, p_sent_at), p_sent_at),
        last_message = CASE WHEN last_message_at IS NULL OR p_sent_at >= last_message_at
                            THEN p_content ELSE last_message END,
        last_message_at = greatest(coalesce(last_message_at, p_sent_at), p_sent_at),
        status = CASE WHEN p_human_request THEN 'waiting'
                      WHEN status = 'closed' AND assigned_to IS NULL THEN 'active'
                      ELSE status END,
        bot_activated = CASE WHEN p_human_request THEN false
                             WHEN status = 'closed' AND assigned_to IS NULL THEN true
                             ELSE bot_activated END,
        handoff_requested_at = CASE WHEN p_human_request THEN p_sent_at ELSE handoff_requested_at END,
        handoff_reason = CASE WHEN p_human_request THEN 'customer_requested_human' ELSE handoff_reason END,
        updated_at = now()
    WHERE id = v_conversation.id
    RETURNING * INTO v_conversation;

    RETURN jsonb_build_object(
        'inserted', true, 'conversation_id', v_conversation.id,
        'should_reply', NOT p_human_request AND v_conversation.status = 'active'
                        AND v_conversation.assigned_to IS NULL
                        AND v_conversation.bot_activated IS DISTINCT FROM false
    );
END;
$$;
REVOKE ALL ON FUNCTION public.ycloud_ingest_inbound(text,uuid,text,text,text,text,timestamptz,boolean)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.ycloud_ingest_inbound(text,uuid,text,text,text,text,timestamptz,boolean)
    TO service_role;

-- A delivery update can arrive before the send request stores the provider ID.
-- Both paths lock that ID, so the pending status is attached exactly once.
CREATE TABLE IF NOT EXISTS public.ycloud_pending_statuses (
    external_id text PRIMARY KEY,
    provider_status text NOT NULL,
    waba_id text,
    sender_number text,
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ycloud_pending_statuses_updated_at
    ON public.ycloud_pending_statuses(updated_at);
ALTER TABLE public.ycloud_pending_statuses ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.ycloud_pending_statuses FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.ycloud_pending_statuses TO service_role;

CREATE OR REPLACE FUNCTION public.ycloud_record_status(
    p_external_id text, p_status text, p_waba_id text DEFAULT NULL, p_from text DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql
SET search_path = public
AS $$
DECLARE
    v_message public.mensagens%ROWTYPE;
    v_conversation public.conversas%ROWTYPE;
    v_channel public.canais%ROWTYPE;
    v_current_rank integer;
    v_incoming_rank integer;
BEGIN
    v_incoming_rank := CASE p_status WHEN 'accepted' THEN 0 WHEN 'sent' THEN 1
        WHEN 'failed' THEN 2 WHEN 'delivered' THEN 3 WHEN 'read' THEN 4 ELSE -1 END;
    IF v_incoming_rank < 0 OR p_external_id IS NULL OR p_external_id = '' THEN
        RETURN jsonb_build_object('updated', false);
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(p_external_id, 0));
    SELECT * INTO v_message FROM public.mensagens WHERE external_id = p_external_id FOR UPDATE;
    IF NOT FOUND THEN
        INSERT INTO public.ycloud_pending_statuses
            (external_id, provider_status, waba_id, sender_number)
        VALUES (p_external_id, p_status, p_waba_id, p_from)
        ON CONFLICT (external_id) DO UPDATE SET
            provider_status = CASE WHEN
                CASE excluded.provider_status WHEN 'accepted' THEN 0 WHEN 'sent' THEN 1
                    WHEN 'failed' THEN 2 WHEN 'delivered' THEN 3 WHEN 'read' THEN 4 END
                > CASE ycloud_pending_statuses.provider_status
                    WHEN 'accepted' THEN 0 WHEN 'sent' THEN 1 WHEN 'failed' THEN 2
                    WHEN 'delivered' THEN 3 WHEN 'read' THEN 4 END
                THEN excluded.provider_status ELSE ycloud_pending_statuses.provider_status END,
            waba_id = coalesce(excluded.waba_id, ycloud_pending_statuses.waba_id),
            sender_number = coalesce(excluded.sender_number, ycloud_pending_statuses.sender_number),
            updated_at = now();
        DELETE FROM public.ycloud_pending_statuses WHERE updated_at < now() - interval '7 days';
        RETURN jsonb_build_object('updated', false, 'pending', true);
    END IF;

    SELECT * INTO v_conversation FROM public.conversas WHERE id = v_message.conversa_id;
    SELECT * INTO v_channel FROM public.canais WHERE id = v_conversation.canal_id;
    IF v_conversation.provider IS DISTINCT FROM 'ycloud'
       OR v_channel.provider IS DISTINCT FROM 'ycloud'
       OR v_channel.workspace_id IS DISTINCT FROM v_conversation.workspace_id
       OR (p_waba_id IS NOT NULL AND p_waba_id <> v_channel.waba_id)
       OR (p_from IS NOT NULL AND regexp_replace(p_from, '[^0-9]', '', 'g')
           <> regexp_replace(coalesce(v_channel.display_phone, ''), '[^0-9]', '', 'g')) THEN
        RETURN jsonb_build_object('updated', false);
    END IF;
    v_current_rank := CASE v_message.provider_status WHEN 'accepted' THEN 0
        WHEN 'sent' THEN 1 WHEN 'failed' THEN 2 WHEN 'delivered' THEN 3
        WHEN 'read' THEN 4 ELSE -1 END;
    IF v_incoming_rank <= v_current_rank THEN
        RETURN jsonb_build_object('updated', false);
    END IF;
    UPDATE public.mensagens SET provider_status = p_status,
        status = CASE WHEN p_status = 'accepted' THEN 'sending' ELSE p_status END
    WHERE id = v_message.id;
    RETURN jsonb_build_object('updated', true, 'conversation_id', v_conversation.id,
                              'workspace_id', v_conversation.workspace_id);
END;
$$;
REVOKE ALL ON FUNCTION public.ycloud_record_status(text,text,text,text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.ycloud_record_status(text,text,text,text) TO service_role;

CREATE OR REPLACE FUNCTION public.ycloud_attach_outbound(
    p_message_id uuid, p_external_id text, p_workspace_id uuid
) RETURNS jsonb
LANGUAGE plpgsql
SET search_path = public
AS $$
DECLARE
    v_message public.mensagens%ROWTYPE;
    v_conversation public.conversas%ROWTYPE;
    v_channel public.canais%ROWTYPE;
    v_pending public.ycloud_pending_statuses%ROWTYPE;
    v_status text := 'accepted';
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_external_id, 0));
    SELECT * INTO v_message FROM public.mensagens WHERE id = p_message_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'YCloud outgoing message missing'; END IF;
    SELECT * INTO v_conversation FROM public.conversas WHERE id = v_message.conversa_id;
    SELECT * INTO v_channel FROM public.canais WHERE id = v_conversation.canal_id;
    IF v_conversation.provider IS DISTINCT FROM 'ycloud'
       OR v_conversation.workspace_id IS DISTINCT FROM p_workspace_id
       OR v_channel.provider IS DISTINCT FROM 'ycloud'
       OR v_channel.workspace_id IS DISTINCT FROM p_workspace_id THEN
        RAISE EXCEPTION 'YCloud outgoing channel mismatch';
    END IF;
    SELECT * INTO v_pending FROM public.ycloud_pending_statuses WHERE external_id = p_external_id;
    IF FOUND THEN
        IF (v_pending.waba_id IS NULL OR v_pending.waba_id = v_channel.waba_id)
           AND (v_pending.sender_number IS NULL OR
                regexp_replace(v_pending.sender_number, '[^0-9]', '', 'g') =
                regexp_replace(coalesce(v_channel.display_phone, ''), '[^0-9]', '', 'g')) THEN
            v_status := v_pending.provider_status;
        END IF;
        DELETE FROM public.ycloud_pending_statuses WHERE external_id = p_external_id;
    END IF;
    UPDATE public.mensagens SET external_id = p_external_id,
        provider_status = v_status,
        status = CASE WHEN v_status = 'accepted' THEN 'sending' ELSE v_status END
    WHERE id = p_message_id
    RETURNING * INTO v_message;
    RETURN to_jsonb(v_message);
END;
$$;
REVOKE ALL ON FUNCTION public.ycloud_attach_outbound(uuid,text,uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.ycloud_attach_outbound(uuid,text,uuid) TO service_role;

-- The existing global unique index on mensagens.external_id also covers ycloud:<id>.
-- The existing conversation index already includes workspace_id, channel and canal_id.

CREATE OR REPLACE VIEW public.conversation_contact_inbox
WITH (security_invoker = true) AS
WITH identified AS (
    SELECT c.*,
        CASE
            WHEN c.channel IN ('whatsapp','sms') AND
                length(regexp_replace(coalesce(c.contact_phone,''),'[^0-9]','','g')) BETWEEN 10 AND 15
                THEN 'phone:' || regexp_replace(c.contact_phone,'[^0-9]','','g')
            WHEN nullif(btrim(c.contact_phone),'') IS NOT NULL
                THEN 'contact:' || btrim(c.contact_phone)
            ELSE 'session:' || c.id::text
        END AS contact_key
    FROM public.conversas c
    WHERE c.workspace_id IS NOT NULL AND c.merged_into IS NULL
), grouped AS (
    SELECT workspace_id, channel, coalesce(canal_id,'') AS channel_connection, contact_key,
        (array_agg(id ORDER BY created_at,id))[1] AS id,
        array_agg(id ORDER BY created_at,id) AS session_ids,
        (array_agg(id ORDER BY (status <> 'closed') DESC,
            last_message_at DESC NULLS LAST, created_at DESC,id))[1] AS active_session_id,
        (array_agg(last_message ORDER BY last_message_at DESC NULLS LAST,created_at DESC,id))[1] AS last_message,
        max(coalesce(last_message_at,created_at)) AS last_message_at,
        sum(coalesce(unread_count,0)) FILTER (WHERE status <> 'closed') AS unread_count,
        count(*) FILTER (WHERE status <> 'closed') AS open_sessions,
        count(*) FILTER (WHERE status = 'waiting' AND nullif(assigned_to,'') IS NULL
            AND handoff_requested_at IS NOT NULL
            AND handoff_reason IN ('customer_requested_human','customer_accepted_handoff_offer','bot_unavailable')) AS waiting_sessions,
        CASE WHEN count(DISTINCT coalesce(assigned_to,'')) FILTER (WHERE status <> 'closed') = 1
            THEN min(nullif(assigned_to,'')) FILTER (WHERE status <> 'closed') END AS contact_assignee,
        max(handoff_requested_at) FILTER (WHERE status = 'waiting' AND nullif(assigned_to,'') IS NULL
            AND handoff_requested_at IS NOT NULL
            AND handoff_reason IN ('customer_requested_human','customer_accepted_handoff_offer','bot_unavailable')) AS handoff_requested_at,
        (array_agg(handoff_reason ORDER BY handoff_requested_at DESC) FILTER (WHERE status = 'waiting'
            AND nullif(assigned_to,'') IS NULL AND handoff_requested_at IS NOT NULL
            AND handoff_reason IN ('customer_requested_human','customer_accepted_handoff_offer','bot_unavailable')))[1] AS handoff_reason
    FROM identified
    GROUP BY workspace_id,channel,coalesce(canal_id,''),contact_key
)
SELECT g.workspace_id,g.channel,g.channel_connection,g.contact_key,g.id,g.session_ids,
    g.active_session_id,g.last_message,g.last_message_at,g.unread_count,g.open_sessions,
    g.waiting_sessions,g.contact_assignee, to_jsonb(c) || jsonb_build_object(
    'assigned_to', g.contact_assignee,
    'handoff_requested_at', g.handoff_requested_at,
    'handoff_reason', g.handoff_reason,
    'status', CASE WHEN g.open_sessions = 0 THEN 'closed'
                   WHEN g.contact_assignee IS NOT NULL THEN 'active'
                   WHEN g.waiting_sessions > 0 THEN 'waiting' ELSE 'active' END
) AS current_session
FROM grouped g JOIN public.conversas c ON c.id=g.active_session_id;

REVOKE ALL ON public.conversation_contact_inbox FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.conversation_contact_inbox TO service_role;
NOTIFY pgrst, 'reload schema';
