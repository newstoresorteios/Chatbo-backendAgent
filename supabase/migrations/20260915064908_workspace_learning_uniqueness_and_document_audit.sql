DROP INDEX IF EXISTS public.uq_ai_instruction_extension_active_key;
CREATE UNIQUE INDEX uq_ai_instruction_extension_active_key ON public.ai_agent_instruction_extensions
 (tenant_id,coalesce(workspace_id,'00000000-0000-0000-0000-000000000000'::uuid),scope,scope_key_norm,extension_key)
 WHERE status='active';

CREATE TABLE public.agent_persona_attachment_history (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 attachment_id uuid NOT NULL, workspace_id uuid NOT NULL, operation text NOT NULL,
 previous_value jsonb, new_value jsonb, recorded_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.agent_persona_attachment_history ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.agent_persona_attachment_history FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT ON public.agent_persona_attachment_history TO service_role;
GRANT USAGE ON SEQUENCE public.agent_persona_attachment_history_id_seq TO service_role;
CREATE INDEX ON public.agent_persona_attachment_history(workspace_id,attachment_id,recorded_at DESC);
CREATE FUNCTION public.audit_persona_attachment_change() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path=public,pg_temp AS $$
BEGIN
 INSERT INTO agent_persona_attachment_history(attachment_id,workspace_id,operation,previous_value,new_value)
 VALUES(coalesce(NEW.id,OLD.id),coalesce(NEW.workspace_id,OLD.workspace_id),TG_OP,
 CASE WHEN TG_OP<>'INSERT' THEN to_jsonb(OLD)-'storage_path' END,
 CASE WHEN TG_OP<>'DELETE' THEN to_jsonb(NEW)-'storage_path' END);
 RETURN coalesce(NEW,OLD);
END; $$;
REVOKE ALL ON FUNCTION public.audit_persona_attachment_change() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.audit_persona_attachment_change() TO service_role;
CREATE TRIGGER persona_attachment_audit AFTER INSERT OR UPDATE OR DELETE ON public.agent_persona_attachments
FOR EACH ROW EXECUTE FUNCTION public.audit_persona_attachment_change();
