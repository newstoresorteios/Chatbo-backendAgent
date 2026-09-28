-- Isola o catálogo operacional da Mai sem alterar os valores publicados da NS.
-- O catálogo-base continua único; presentation/defaults específicos pertencem
-- à configuração versionada do workspace XNamai.

CREATE OR REPLACE FUNCTION pg_temp.mai_personalize(value TEXT)
RETURNS TEXT
LANGUAGE SQL
IMMUTABLE
AS $fn$
  SELECT replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(
    COALESCE(value, ''),
    'https://www.sorteionewstore.com.br/', 'https://www.xnamai.com/'),
    'https://www.newstorerj.com.br/', 'https://xnamai.meuspedidos.com.br/'),
    'https://www.newstorerj.com/', 'https://xnamai.meuspedidos.com.br/'),
    'NewStoreAgent', 'Mai Agent'),
    'AgenteNewStore', 'Mai Agent'),
    'NewStore', 'XNamai'),
    'New Store', 'XNamai'),
    'TrayAdapter', 'MercosAdaptor'),
    'Tray', 'Mercos'),
    'Brevo', 'YCloud'),
    'Crono', 'Mai'),
    'Relógios', 'Produtos'),
    'relógios', 'produtos')
$fn$;

INSERT INTO public.agent_runtime_types(code, name, base_runtime, description)
VALUES (
  'mai_agent',
  'Mai Agent',
  'nsagent',
  'Mai — agente comercial da XNamai com MercosAdaptor e YCloud'
)
ON CONFLICT (code) DO UPDATE
SET name = EXCLUDED.name,
    base_runtime = EXCLUDED.base_runtime,
    description = EXCLUDED.description;

DO $migration$
DECLARE
  v_workspace CONSTANT UUID := 'aa774d20-509f-4d54-865b-7a5de22b6d30';
  v_current_version INTEGER;
  v_overrides JSONB;
  v_values JSONB;
  v_configuration JSONB;
BEGIN
  UPDATE public.workspace_agents
  SET agent_type = 'mai_agent',
      display_name = 'Mai Agent',
      status = 'active',
      updated_at = NOW()
  WHERE workspace_id = v_workspace;

  SELECT config_version INTO v_current_version
  FROM public.workspace_agents
  WHERE workspace_id = v_workspace;

  IF v_current_version IS NULL THEN
    RAISE EXCEPTION 'workspace_agent ausente para XNamai';
  END IF;

  -- Uma configuração já publicada pelo operador é soberana e não deve ser
  -- sobrescrita por reexecução da migration.
  IF v_current_version > 0 THEN
    RETURN;
  END IF;

  WITH catalog AS (
    SELECT
      key,
      definition,
      (
        key LIKE 'message.%'
        OR key LIKE 'tray\_%' ESCAPE '\'
        OR key ILIKE '%raffle%'
        OR key ILIKE '%gift%'
        OR key IN (
          'agent_catalog_index_fallback_to_tray',
          'business.credit_bands',
          'historyEvaluationRepairTarget'
        )
        OR lower(COALESCE(definition->>'label', '')) LIKE '%cartão presente%'
        OR lower(COALESCE(definition->>'label', '')) LIKE '%cartao presente%'
        OR lower(COALESCE(definition->>'label', '')) LIKE '%sorteio%'
        OR lower(COALESCE(definition->>'group', '')) LIKE '%cartão presente%'
        OR lower(COALESCE(definition->>'group', '')) LIKE '%sorteio%'
      ) AS hidden,
      CASE key
        WHEN 'app_name' THEN to_jsonb('MaiAgent'::TEXT)
        WHEN 'openai_agent_name' THEN to_jsonb('MaiAgent'::TEXT)
        WHEN 'business.agent_name' THEN to_jsonb('Mai'::TEXT)
        WHEN 'business.site_url' THEN to_jsonb('https://www.xnamai.com/'::TEXT)
        WHEN 'business.store_url' THEN to_jsonb('https://xnamai.meuspedidos.com.br/'::TEXT)
        WHEN 'business.store_pronta_entrega_url' THEN to_jsonb('https://xnamai.meuspedidos.com.br/'::TEXT)
        WHEN 'agent_trusted_fact_domains' THEN to_jsonb('xnamai.com,www.xnamai.com,xnamai.meuspedidos.com.br,clubxnamai.com.br,www.clubxnamai.com.br'::TEXT)
        WHEN 'storefrontHosts' THEN to_jsonb('["xnamai.meuspedidos.com.br", "www.xnamai.com", "www.clubxnamai.com.br"]'::TEXT)
        WHEN 'business.greeting_variants' THEN to_jsonb('["Oi! Sou a {agent_name}, da XNamai. Como posso ajudar?", "Olá! Sou a {agent_name}, consultora digital da XNamai — o que você procura?", "Oi! Como posso ajudar com produtos, pedidos ou o XNaMai Club?"]'::TEXT)
        WHEN 'business.institutional_knowledge' THEN to_jsonb('[{"title":"Sobre a XNamai","cues":["xnamai","empresa","loja","distribuidora","atacado"],"body":"A XNamai é uma distribuidora de eletrônicos e acessórios para celular com atuação no atacado. Site institucional: https://www.xnamai.com/."},{"title":"Catálogo e pedidos","cues":["catálogo","catalogo","produto","preço","preco","estoque","pedido","comprar"],"body":"O catálogo e portal oficial de pedidos é https://xnamai.meuspedidos.com.br/. Preço, estoque, compatibilidade, pedido mínimo, frete, pagamento e prazo devem ser confirmados no catálogo, no MercosAdaptor ou com a equipe."},{"title":"XNaMai Club","cues":["club","clube","membro","assinatura","plano","benefício","beneficio"],"body":"O XNaMai Club oferece condições exclusivas em compras elegíveis para membros com assinatura ativa. Consulte regras e planos atuais em https://www.clubxnamai.com.br/. Não prometa desconto ou benefício sem confirmação oficial."},{"title":"Atendimento humano","cues":["atendente","humano","equipe","suporte","falar com alguém","falar com alguem"],"body":"Quando a solicitação exigir análise humana, encaminhe para a equipe da XNamai. Não invente telefone, endereço ou contato; use somente os canais oficiais confirmados."}]'::TEXT)
        WHEN 'adaptiveDiscoveryRules' THEN to_jsonb('{"reviewAfterQuestions":3,"maxSearches":4,"candidateLimit":20,"cacheTtlSeconds":300,"facets":[{"slot":"color","fields":["color"]},{"slot":"budget","fields":["current_price","price"]},{"slot":"occasion","fields":["occasion"]}],"criteriaLabels":{"brand":"marca","color":"cor","budget":"orçamento máximo","occasion":"uso"},"showResultsPattern":"\\b(?:mostra|mostre|manda|mande)\\s+(?:o que|as opções|as opcoes|os produtos)|\\b(?:pode escolher|sem mais perguntas)\\b"}'::TEXT)
        ELSE CASE jsonb_typeof(definition->'default')
          WHEN 'string' THEN to_jsonb(pg_temp.mai_personalize(definition->>'default'))
          ELSE definition->'default'
        END
      END AS personalized_default
    FROM public.agent_configuration_catalog
  )
  SELECT
    jsonb_object_agg(
      key,
      CASE WHEN hidden THEN jsonb_build_object('hidden', TRUE)
      ELSE jsonb_strip_nulls(jsonb_build_object(
        'default', personalized_default,
        'label', pg_temp.mai_personalize(definition->>'label'),
        'description', pg_temp.mai_personalize(definition->>'description')
      )) END
    ),
    jsonb_object_agg(key, personalized_default) FILTER (WHERE NOT hidden)
  INTO v_overrides, v_values
  FROM catalog;

  v_configuration := jsonb_build_object(
    'schemaVersion', 2,
    'agentIdentity', jsonb_build_object(
      'agentType', 'mai_agent',
      'displayName', 'Mai Agent',
      'personaName', 'Mai',
      'brand', 'XNamai',
      'commerceProvider', 'mercos',
      'commerceAdaptor', 'MercosAdaptor',
      'whatsappProvider', 'ycloud'
    ),
    'catalogOverrides', v_overrides,
    'runtime', jsonb_build_object(
      'schemaVersion', 2,
      'values', v_values
    )
  );

  PERFORM public.publish_workspace_agent_config(
    v_workspace,
    v_configuration,
    'migration:mai-agent-workspace-initial-v1',
    0
  );
END
$migration$;
