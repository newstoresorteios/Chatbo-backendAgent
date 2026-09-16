-- Only confirmed customer handoffs are part of the human waiting queue.
ALTER TABLE public.conversas ADD COLUMN IF NOT EXISTS handoff_requested_at timestamptz;
ALTER TABLE public.conversas ADD COLUMN IF NOT EXISTS handoff_reason text;
COMMENT ON COLUMN public.conversas.handoff_requested_at IS 'Time of a direct customer request or accepted human handoff offer; not an ordinary inbound.';

-- Preserve legacy pending handoffs only where the server audit records customer consent.
WITH evidence AS (
    SELECT DISTINCT ON (a.entity_id) a.entity_id,a.workspace_id,a.created_at,
        a.original_row #>> '{_handoff,reason}' AS reason
    FROM public.conversation_reconciliation_audit a
    WHERE a.entity_type='conversation' AND a.original_row ? '_handoff'
    ORDER BY a.entity_id,a.created_at DESC,a.id DESC
)
UPDATE public.conversas c SET handoff_requested_at=e.created_at,handoff_reason=e.reason
FROM evidence e WHERE c.id=e.entity_id AND c.workspace_id=e.workspace_id
    AND c.status='waiting' AND nullif(c.assigned_to,'') IS NULL
    AND c.handoff_requested_at IS NULL
    AND e.reason IN ('customer_requested_human','customer_accepted_handoff_offer');

-- Read model only: original sessions, messages and agent identities stay intact.
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
        count(*) FILTER (WHERE status = 'waiting' AND nullif(assigned_to,'') IS NULL AND handoff_requested_at IS NOT NULL AND handoff_reason IN ('customer_requested_human','customer_accepted_handoff_offer')) AS waiting_sessions,
        CASE WHEN count(DISTINCT coalesce(assigned_to,'')) FILTER (WHERE status <> 'closed') = 1
            THEN min(nullif(assigned_to,'')) FILTER (WHERE status <> 'closed') END AS contact_assignee,
        max(handoff_requested_at) FILTER (WHERE status = 'waiting' AND nullif(assigned_to,'') IS NULL AND handoff_requested_at IS NOT NULL AND handoff_reason IN ('customer_requested_human','customer_accepted_handoff_offer')) AS handoff_requested_at,
        (array_agg(handoff_reason ORDER BY handoff_requested_at DESC) FILTER (WHERE status = 'waiting' AND nullif(assigned_to,'') IS NULL AND handoff_requested_at IS NOT NULL AND handoff_reason IN ('customer_requested_human','customer_accepted_handoff_offer')))[1] AS handoff_reason
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

REVOKE ALL ON public.conversation_contact_inbox FROM PUBLIC,anon,authenticated;
GRANT SELECT ON public.conversation_contact_inbox TO service_role;
COMMENT ON VIEW public.conversation_contact_inbox IS
    'One inbox entry per verified contact, workspace and channel connection; session history is preserved.';

INSERT INTO public.agent_configuration_catalog(key,definition) VALUES ('message.handoff_offer', '{"key": "message.handoff_offer", "target": "message", "type": "textarea", "label": "Confirmação antes de transferir para humano", "group": "Atendimento humano", "description": "Pergunta se o cliente aceita falar com um atendente quando a IA precisa de ajuda. A fila só é acionada após o aceite.", "maxLength": 4000, "default": "Para continuar com esse assunto, preciso da ajuda de um atendente. Quer que eu encaminhe seu atendimento para a equipe?"}'::jsonb) ON CONFLICT (key) DO NOTHING;
NOTIFY pgrst, 'reload schema';
