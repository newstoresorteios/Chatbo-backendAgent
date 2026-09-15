-- Link historical publications only where both real identifiers agree.
UPDATE public.ai_agent_persona_versions v SET workspace_id=p.workspace_id
FROM public.agent_personas p
WHERE v.metadata->>'chatboPersonaId'=p.id::text
  AND v.metadata->>'chatboWorkspaceId'=p.workspace_id::text
  AND v.workspace_id IS NULL;
-- Quarantine invalid active fixtures, retaining their audit history.
UPDATE public.ai_agent_persona_versions v SET status='archived', archived_at=now()
WHERE status='active' AND metadata->>'publishedFrom'='chatbo-backendAgent'
  AND NOT EXISTS (SELECT FROM public.agent_personas p
    WHERE p.id::text=v.metadata->>'chatboPersonaId'
      AND p.workspace_id=v.workspace_id
      AND p.workspace_id::text=v.metadata->>'chatboWorkspaceId');
DROP INDEX IF EXISTS public.uq_ai_agent_persona_active;
CREATE UNIQUE INDEX uq_ai_agent_persona_active
ON public.ai_agent_persona_versions(tenant_id,persona_key,COALESCE(workspace_id,'00000000-0000-0000-0000-000000000000'::uuid))
WHERE status='active';

CREATE OR REPLACE FUNCTION public.validate_agent_persona_link() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=public,pg_temp AS $$
BEGIN
 IF NEW.status='active' AND NEW.metadata->>'publishedFrom'='chatbo-backendAgent' THEN
  IF NEW.workspace_id IS NULL OR NOT EXISTS(
    SELECT FROM public.agent_personas p JOIN public.workspace_agents a ON a.workspace_id=p.workspace_id
    WHERE p.id::text=NEW.metadata->>'chatboPersonaId'
      AND p.workspace_id=NEW.workspace_id
      AND p.workspace_id::text=NEW.metadata->>'chatboWorkspaceId'
      AND a.status='active' AND a.agent_type='nsagent'
  ) THEN RAISE EXCEPTION 'invalid_persona_workspace_link' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.validate_agent_persona_link() FROM PUBLIC,anon,authenticated;
CREATE TRIGGER validate_agent_persona_link BEFORE INSERT OR UPDATE ON public.ai_agent_persona_versions
FOR EACH ROW EXECUTE FUNCTION public.validate_agent_persona_link();

CREATE OR REPLACE FUNCTION public.publish_nsagent_persona(
 p_workspace_id uuid, p_persona_id uuid, p_expected_profile_version integer,
 p_tenant_id text, p_persona_key text, p_instructions text, p_instructions_hash text,
 p_activated_by text DEFAULT NULL, p_knowledge_docs integer DEFAULT 0
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public,pg_temp AS $$
DECLARE p public.agent_personas%ROWTYPE; old_p public.agent_personas%ROWTYPE;
 v public.ai_agent_persona_versions%ROWTYPE; next_version integer; archived integer;
BEGIN
 -- Serialize version allocation and publication; key includes the runtime identity.
 PERFORM pg_advisory_xact_lock(hashtextextended(p_tenant_id || ':' || p_persona_key,0));
 SELECT * INTO p FROM public.agent_personas WHERE id=p_persona_id AND workspace_id=p_workspace_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'invalid_persona_workspace_link' USING ERRCODE='23514'; END IF;
 IF p.version<>p_expected_profile_version THEN RAISE EXCEPTION 'persona_version_conflict' USING ERRCODE='40001'; END IF;
 IF NOT EXISTS(SELECT FROM public.workspace_agents WHERE workspace_id=p_workspace_id AND status='active' AND agent_type='nsagent')
 THEN RAISE EXCEPTION 'inactive_persona_runtime' USING ERRCODE='23514'; END IF;
 IF length(trim(p_instructions))<40 OR p_instructions_hash IS DISTINCT FROM encode(sha256(convert_to(p_instructions,'UTF8')),'hex')
 THEN RAISE EXCEPTION 'invalid_persona_instructions' USING ERRCODE='23514'; END IF;
 SELECT * INTO v FROM public.ai_agent_persona_versions
 WHERE tenant_id=p_tenant_id AND persona_key=p_persona_key AND workspace_id=p_workspace_id
 AND status='active' AND instructions_hash=p_instructions_hash
 AND metadata->>'chatboPersonaId'=p_persona_id::text AND (metadata->>'chatboVersion')::integer=p.version;
 IF FOUND AND p.status='active' THEN
  RETURN jsonb_build_object('published',true,'version',v.version,'nsAgentPersonaId',v.id,
    'archivedPrevious',0,'workspaceId',p_workspace_id,'profileVersion',p.version,'idempotent',true);
 END IF;
 -- Activate the profile in the same transaction as the runtime publication.
 IF p.status<>'active' THEN
  FOR old_p IN SELECT * FROM public.agent_personas WHERE workspace_id=p_workspace_id AND status='active' AND id<>p.id FOR UPDATE LOOP
   UPDATE public.agent_personas SET status='inactive',version=version+1,deactivated_at=now(),updated_at=now()
   WHERE id=old_p.id RETURNING * INTO old_p;
   INSERT INTO public.agent_persona_versions(persona_id,workspace_id,version,snapshot,change_type)
   VALUES(old_p.id,old_p.workspace_id,old_p.version,to_jsonb(old_p),'deactivated');
  END LOOP;
  UPDATE public.agent_personas SET status='active',version=version+1,activated_at=now(),deactivated_at=NULL,updated_at=now()
  WHERE id=p.id RETURNING * INTO p;
  INSERT INTO public.agent_persona_versions(persona_id,workspace_id,version,snapshot,change_type)
  VALUES(p.id,p.workspace_id,p.version,to_jsonb(p),'activated');
 END IF;
 UPDATE public.ai_agent_persona_versions SET status='archived',archived_at=now()
 WHERE tenant_id=p_tenant_id AND persona_key=p_persona_key AND workspace_id=p_workspace_id AND status='active';
 GET DIAGNOSTICS archived=ROW_COUNT;
 SELECT coalesce(max(version),0)+1 INTO next_version FROM public.ai_agent_persona_versions
 WHERE tenant_id=p_tenant_id AND persona_key=p_persona_key;
 INSERT INTO public.ai_agent_persona_versions(tenant_id,persona_key,workspace_id,version,name,source,instructions,
 instructions_hash,status,created_by,activated_by,activated_at,metadata)
 VALUES(p_tenant_id,p_persona_key,p_workspace_id,next_version,p.name,'user',p_instructions,p_instructions_hash,
 'active',p_activated_by,p_activated_by,now(),jsonb_build_object('chatboPersonaId',p.id,
 'chatboWorkspaceId',p.workspace_id,'chatboVersion',p.version,'publishedFrom','chatbo-backendAgent','knowledgeDocs',p_knowledge_docs))
 RETURNING * INTO v;
 RETURN jsonb_build_object('published',true,'version',v.version,'nsAgentPersonaId',v.id,
 'archivedPrevious',archived,'workspaceId',p_workspace_id,'profileVersion',p.version,'idempotent',false);
END $$;
REVOKE ALL ON FUNCTION public.publish_nsagent_persona(uuid,uuid,integer,text,text,text,text,text,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.publish_nsagent_persona(uuid,uuid,integer,text,text,text,text,text,integer) TO service_role;

-- Recover the last verified publication of the currently active real profile.
-- Recompilation of the current profile follows via the validated publisher.
WITH valid AS (
 SELECT DISTINCT ON(v.tenant_id,v.persona_key,v.workspace_id) v.id
 FROM public.ai_agent_persona_versions v JOIN public.agent_personas p ON p.id::text=v.metadata->>'chatboPersonaId' AND p.workspace_id=v.workspace_id
 WHERE p.status='active' AND NOT EXISTS(SELECT FROM public.ai_agent_persona_versions a
   WHERE a.tenant_id=v.tenant_id AND a.persona_key=v.persona_key AND a.workspace_id=v.workspace_id AND a.status='active')
 ORDER BY v.tenant_id,v.persona_key,v.workspace_id,v.version DESC
) UPDATE public.ai_agent_persona_versions SET status='active',activated_at=now(),archived_at=NULL WHERE id IN(SELECT id FROM valid);
NOTIFY pgrst,'reload schema';
