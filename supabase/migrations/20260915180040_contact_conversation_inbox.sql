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
        count(*) FILTER (WHERE status = 'waiting' AND nullif(assigned_to,'') IS NULL) AS waiting_sessions,
        CASE WHEN count(DISTINCT coalesce(assigned_to,'')) FILTER (WHERE status <> 'closed') = 1
            THEN min(nullif(assigned_to,'')) FILTER (WHERE status <> 'closed') END AS contact_assignee
    FROM identified
    GROUP BY workspace_id,channel,coalesce(canal_id,''),contact_key
)
SELECT g.*, to_jsonb(c) || jsonb_build_object(
    'assigned_to', g.contact_assignee,
    'status', CASE WHEN g.open_sessions = 0 THEN 'closed'
                   WHEN g.contact_assignee IS NOT NULL THEN 'active'
                   WHEN g.waiting_sessions > 0 THEN 'waiting' ELSE 'active' END
) AS current_session
FROM grouped g JOIN public.conversas c ON c.id=g.active_session_id;

REVOKE ALL ON public.conversation_contact_inbox FROM PUBLIC,anon,authenticated;
GRANT SELECT ON public.conversation_contact_inbox TO service_role;
COMMENT ON VIEW public.conversation_contact_inbox IS
    'One inbox entry per verified contact, workspace and channel connection; session history is preserved.';
