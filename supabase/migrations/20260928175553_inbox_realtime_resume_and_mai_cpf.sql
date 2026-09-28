-- Feed the server-side inbox event bridge. The browser remains isolated behind
-- the authenticated /conversas/events endpoint and never receives DB secrets.
DO $migration$
DECLARE
  table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'ai_inbound_messages',
    'ai_agent_responses',
    'conversas',
    'mensagens'
  ]
  LOOP
    IF NOT EXISTS (
      SELECT 1
      FROM pg_publication_tables
      WHERE pubname = 'supabase_realtime'
        AND schemaname = 'public'
        AND tablename = table_name
    ) THEN
      EXECUTE format('ALTER PUBLICATION supabase_realtime ADD TABLE public.%I', table_name);
    END IF;
  END LOOP;
END
$migration$;

-- Publish the CPF rule only in the XNamai workspace. Preserve every operator
-- value and catalog override already saved there, and do not touch NS.
DO $migration$
DECLARE
  agent public.workspace_agents%ROWTYPE;
  next_configuration jsonb;
  next_values jsonb;
  next_overrides jsonb;
  knowledge text := '[{"title":"Sobre a XNamai","cues":["xnamai","empresa","loja","distribuidora","atacado"],"body":"A XNamai é uma distribuidora de eletrônicos e acessórios para celular com atuação no atacado. Site institucional: https://www.xnamai.com/."},{"title":"Cadastro e documentos","cues":["cadastro","cadastrar","cpf","cnpj","pessoa física","pessoa juridica","comprar"],"body":"A XNamai atende cadastro e compras tanto por CPF quanto por CNPJ. Nunca diga que o cadastro é exclusivo para CNPJ, lojistas ou revendedores. Quando o cliente quiser cadastro assistido, solicite CPF ou CNPJ conforme o tipo de pessoa e siga o fluxo seguro de confirmação."},{"title":"Catálogo e pedidos","cues":["catálogo","catalogo","produto","preço","preco","estoque","pedido","comprar"],"body":"O catálogo e portal oficial de pedidos é https://xnamai.meuspedidos.com.br/. Preço, estoque, compatibilidade, pedido mínimo, frete, pagamento e prazo devem ser confirmados no catálogo, no MercosAdaptor ou com a equipe."},{"title":"XNaMai Club","cues":["club","clube","membro","assinatura","plano","benefício","beneficio"],"body":"O XNaMai Club oferece condições exclusivas em compras elegíveis para membros com assinatura ativa. Consulte regras e planos atuais em https://www.clubxnamai.com.br/. Não prometa desconto ou benefício sem confirmação oficial."},{"title":"Atendimento humano","cues":["atendente","humano","equipe","suporte","falar com alguém","falar com alguem"],"body":"Quando a solicitação exigir análise humana, encaminhe para a equipe da XNamai. Não invente telefone, endereço ou contato; use somente os canais oficiais confirmados."}]';
BEGIN
  SELECT *
  INTO agent
  FROM public.workspace_agents
  WHERE workspace_id = 'aa774d20-509f-4d54-865b-7a5de22b6d30'::uuid
    AND agent_type = 'mai_agent'
    AND status = 'active'
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Mai Agent workspace is not active';
  END IF;

  next_values := coalesce(agent.configuration->'runtime'->'values', '{}'::jsonb)
    || jsonb_build_object('business.institutional_knowledge', knowledge);

  next_overrides := coalesce(agent.configuration->'catalogOverrides', '{}'::jsonb)
    || jsonb_build_object(
      'business.institutional_knowledge',
      coalesce(agent.configuration->'catalogOverrides'->'business.institutional_knowledge', '{}'::jsonb)
        || jsonb_build_object('default', knowledge)
    );

  next_configuration := agent.configuration
    || jsonb_build_object('catalogOverrides', next_overrides)
    || jsonb_build_object(
      'runtime',
      coalesce(agent.configuration->'runtime', '{}'::jsonb)
        || jsonb_build_object('schemaVersion', 2, 'values', next_values)
    );

  PERFORM public.publish_workspace_agent_config(
    agent.workspace_id,
    next_configuration,
    'migration:mai-agent-cpf-and-inbox-resume',
    agent.config_version
  );
END
$migration$;
