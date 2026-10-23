-- Coexistence history sync (whatsapp.smb.history): store old messages per contact
-- without unread counts, bot replies or human-handoff side effects. Conversations
-- created only by history start closed, so they stay out of the active queue.
CREATE OR REPLACE FUNCTION public.ycloud_ingest_history(
    p_channel_id text, p_workspace_id uuid, p_external_id text,
    p_customer text, p_customer_name text, p_content text,
    p_sent_at timestamptz, p_direction text
) RETURNS jsonb
LANGUAGE plpgsql
SET search_path = public
AS $$
DECLARE
    v_conversation public.conversas%ROWTYPE;
    v_message_id uuid;
    v_inbound boolean := p_direction = 'inbound';
BEGIN
    IF p_direction NOT IN ('inbound', 'outbound') THEN
        RAISE EXCEPTION 'Invalid history direction';
    END IF;
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
                p_customer_name, 'whatsapp', 'ycloud', 'closed', true,
                0, '', p_sent_at, CASE WHEN v_inbound THEN p_sent_at ELSE NULL END
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
        v_conversation.id, p_workspace_id, p_content,
        CASE WHEN v_inbound THEN 'customer' ELSE 'agent' END, p_direction,
        CASE WHEN v_inbound THEN 'delivered' ELSE 'sent' END,
        CASE WHEN v_inbound THEN 'received' ELSE 'sent' END,
        p_external_id, p_sent_at
    ) ON CONFLICT (external_id) WHERE external_id IS NOT NULL DO NOTHING
      RETURNING id INTO v_message_id;
    IF v_message_id IS NULL THEN
        RETURN jsonb_build_object('inserted', false);
    END IF;

    UPDATE public.conversas SET
        last_customer_message_at = CASE WHEN v_inbound
            THEN greatest(coalesce(last_customer_message_at, p_sent_at), p_sent_at)
            ELSE last_customer_message_at END,
        last_message = CASE WHEN last_message_at IS NULL OR p_sent_at >= last_message_at
                            THEN p_content ELSE last_message END,
        last_message_at = greatest(coalesce(last_message_at, p_sent_at), p_sent_at),
        updated_at = now()
    WHERE id = v_conversation.id;

    RETURN jsonb_build_object('inserted', true, 'conversation_id', v_conversation.id);
END;
$$;
REVOKE ALL ON FUNCTION public.ycloud_ingest_history(text,uuid,text,text,text,text,timestamptz,text)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.ycloud_ingest_history(text,uuid,text,text,text,text,timestamptz,text)
    TO service_role;

NOTIFY pgrst, 'reload schema';
