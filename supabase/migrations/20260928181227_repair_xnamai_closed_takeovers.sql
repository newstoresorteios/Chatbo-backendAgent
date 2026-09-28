-- Normalize sessions closed before the resume fix. New customer activity can
-- reopen these sessions for Mai without retaining an obsolete human owner.
UPDATE public.conversas
SET assigned_to = NULL,
    bot_activated = true,
    updated_at = now()
WHERE workspace_id = 'aa774d20-509f-4d54-865b-7a5de22b6d30'::uuid
  AND status = 'closed'
  AND (assigned_to IS NOT NULL OR bot_activated IS DISTINCT FROM true);
