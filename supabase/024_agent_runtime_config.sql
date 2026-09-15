-- Configuração operacional versionada do agente por workspace.
-- Somente os backends (service role/conexão Postgres) acessam estas tabelas.

ALTER TABLE public.workspace_agents
  ADD COLUMN IF NOT EXISTS config_version INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS public.workspace_agent_config_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_agent_id UUID NOT NULL REFERENCES public.workspace_agents(id) ON DELETE CASCADE,
  workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
  version INTEGER NOT NULL CHECK (version > 0),
  schema_version INTEGER NOT NULL DEFAULT 1 CHECK (schema_version > 0),
  configuration JSONB NOT NULL,
  created_by TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (workspace_agent_id, version)
);

CREATE INDEX IF NOT EXISTS idx_workspace_agent_config_versions_workspace
  ON public.workspace_agent_config_versions(workspace_id, version DESC);

ALTER TABLE public.workspace_agents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.workspace_agent_config_versions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.workspace_agents FROM anon, authenticated;
REVOKE ALL ON TABLE public.workspace_agent_config_versions FROM anon, authenticated;

CREATE OR REPLACE FUNCTION public.publish_workspace_agent_config(
  p_workspace_id UUID,
  p_configuration JSONB,
  p_created_by TEXT,
  p_expected_version INTEGER
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_agent public.workspace_agents%ROWTYPE;
  v_next_version INTEGER;
BEGIN
  SELECT * INTO v_agent
  FROM public.workspace_agents
  WHERE workspace_id = p_workspace_id
  FOR UPDATE;

  IF NOT FOUND THEN
    INSERT INTO public.workspace_agents (workspace_id, agent_type, status, configuration)
    VALUES (p_workspace_id, 'nsagent', 'active', '{}'::jsonb)
    RETURNING * INTO v_agent;
  END IF;

  IF v_agent.config_version <> p_expected_version THEN
    RAISE EXCEPTION 'config_version_conflict expected=% actual=%',
      p_expected_version, v_agent.config_version USING ERRCODE = '40001';
  END IF;

  v_next_version := v_agent.config_version + 1;

  INSERT INTO public.workspace_agent_config_versions (
    workspace_agent_id, workspace_id, version, schema_version, configuration, created_by
  ) VALUES (
    v_agent.id,
    p_workspace_id,
    v_next_version,
    COALESCE((p_configuration->>'schemaVersion')::INTEGER, 1),
    p_configuration,
    NULLIF(trim(p_created_by), '')
  );

  UPDATE public.workspace_agents
  SET configuration = p_configuration,
      config_version = v_next_version,
      updated_at = NOW()
  WHERE id = v_agent.id;

  RETURN jsonb_build_object('workspaceAgentId', v_agent.id, 'version', v_next_version);
END;
$$;

REVOKE ALL ON FUNCTION public.publish_workspace_agent_config(UUID, JSONB, TEXT, INTEGER) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.publish_workspace_agent_config(UUID, JSONB, TEXT, INTEGER) TO service_role;
