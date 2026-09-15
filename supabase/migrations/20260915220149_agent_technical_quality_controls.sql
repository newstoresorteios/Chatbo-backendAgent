-- Operator-editable technical requirements, review policy and response templates.
-- Existing published workspace overrides are preserved. Apply before releasing NSAgent.
BEGIN;
INSERT INTO public.agent_configuration_catalog (key, definition, updated_at)
SELECT entry->>'key', entry, now()
FROM jsonb_array_elements($quality_catalog$
[
  {
    "key": "catalogTechnicalFeatures",
    "attribute": "catalogTechnicalFeatures",
    "target": "policy",
    "label": "Características técnicas e sinônimos",
    "default": "[{\"field\": \"mechanism\", \"value\": \"automatic\", \"label\": \"automático\", \"aliases\": [\"automático\", \"automatic\", \"automatico\", \"automáticos\", \"automatics\", \"powermatic\"], \"query\": \"automático\", \"evidenceFields\": [\"mechanism\", \"movement\", \"movimento\"]}, {\"field\": \"mechanism\", \"value\": \"quartz\", \"label\": \"quartzo\", \"aliases\": [\"quartzo\", \"quartz\"], \"query\": \"quartzo\", \"evidenceFields\": [\"mechanism\", \"movement\", \"movimento\"]}, {\"field\": \"mechanism\", \"value\": \"solar\", \"label\": \"solar\", \"aliases\": [\"solar\", \"eco-drive\", \"eco drive\"], \"query\": \"solar\", \"evidenceFields\": [\"mechanism\", \"movement\", \"movimento\"]}, {\"field\": \"mechanism\", \"value\": \"manual\", \"label\": \"corda manual\", \"aliases\": [\"corda manual\", \"manual winding\", \"hand winding\"], \"query\": \"manual\", \"evidenceFields\": [\"mechanism\", \"movement\", \"movimento\"]}, {\"field\": \"crystal\", \"value\": \"sapphire\", \"label\": \"cristal de safira\", \"aliases\": [\"safira\", \"sapphire\"], \"query\": \"safira\", \"evidenceFields\": [\"crystal\", \"glass\", \"cristal\", \"vidro\"]}, {\"field\": \"crystal\", \"value\": \"mineral\", \"label\": \"cristal mineral\", \"aliases\": [\"mineral\", \"hardlex\"], \"query\": \"mineral\", \"evidenceFields\": [\"crystal\", \"glass\", \"cristal\", \"vidro\"]}]",
    "type": "textarea",
    "group": "Qualidade e critérios técnicos",
    "description": "Política publicada no banco, aplicada por atendimento.",
    "maxLength": 30000,
    "valueSchema": "technicalFeatures"
  },
  {
    "key": "catalogFeatureRelaxationPhrases",
    "attribute": "catalogFeatureRelaxationPhrases",
    "target": "policy",
    "label": "Expressões que dispensam uma característica",
    "default": "[\"não precisa ser {feature}\", \"não precisa de {feature}\", \"não precisa ter {feature}\", \"pode ser sem {feature}\", \"sem exigência de {feature}\"]",
    "type": "textarea",
    "group": "Qualidade e critérios técnicos",
    "description": "Política publicada no banco, aplicada por atendimento.",
    "maxLength": 6000,
    "valueSchema": "featurePhrases"
  },
  {
    "key": "catalogFeatureNegationPhrases",
    "attribute": "catalogFeatureNegationPhrases",
    "target": "policy",
    "label": "Expressões que negam uma característica",
    "default": "[\"não é {feature}\", \"não tem {feature}\", \"sem {feature}\", \"não quero {feature}\"]",
    "type": "textarea",
    "group": "Qualidade e critérios técnicos",
    "description": "Política publicada no banco, aplicada por atendimento.",
    "maxLength": 6000,
    "valueSchema": "featurePhrases"
  },
  {
    "key": "catalogTechnicalDetailLimit",
    "attribute": "catalogTechnicalDetailLimit",
    "target": "policy",
    "label": "Máximo de fichas técnicas por consulta",
    "default": 8,
    "type": "integer",
    "group": "Qualidade e critérios técnicos",
    "description": "Política publicada no banco, aplicada por atendimento.",
    "min": 1,
    "max": 40
  },
  {
    "key": "catalogTechnicalSearchLimit",
    "attribute": "catalogTechnicalSearchLimit",
    "target": "policy",
    "label": "Buscas adicionais por característica",
    "default": 2,
    "type": "integer",
    "group": "Qualidade e critérios técnicos",
    "description": "Política publicada no banco, aplicada por atendimento.",
    "min": 0,
    "max": 6
  },
  {
    "key": "catalogTechnicalConcurrency",
    "attribute": "catalogTechnicalConcurrency",
    "target": "policy",
    "label": "Consultas de ficha simultâneas",
    "default": 2,
    "type": "integer",
    "group": "Qualidade e critérios técnicos",
    "description": "Política publicada no banco, aplicada por atendimento.",
    "min": 1,
    "max": 5
  },
  {
    "key": "critiqueUnavailableAction",
    "attribute": "critiqueUnavailableAction",
    "target": "policy",
    "label": "Conduta quando o revisor não pode executar",
    "default": "grounded_fallback",
    "type": "select",
    "group": "Qualidade e critérios técnicos",
    "description": "Política publicada no banco, aplicada por atendimento.",
    "options": [
      {
        "value": "grounded_fallback",
        "label": "Resposta com fatos validados"
      },
      {
        "value": "handoff",
        "label": "Encaminhar para revisão humana"
      }
    ]
  },
  {
    "key": "catalogReserveReviewCall",
    "attribute": "catalogReserveReviewCall",
    "target": "policy",
    "label": "Reservar chamada para revisão do catálogo",
    "default": true,
    "type": "boolean",
    "group": "Qualidade e critérios técnicos",
    "description": "Política publicada no banco, aplicada por atendimento."
  },
  {
    "key": "message.critique_handoff",
    "attribute": "critique_handoff",
    "target": "message",
    "label": "Encaminhamento por falha de revisão",
    "default": "Vou solicitar ajuda da equipe para continuar seu atendimento com os critérios que você informou.",
    "type": "textarea",
    "maxLength": 12000,
    "group": "Qualidade e critérios técnicos",
    "description": "Texto editável no banco; preserve as variáveis indicadas."
  },
  {
    "key": "message.catalog_requirements_unknown",
    "attribute": "catalog_requirements_unknown",
    "target": "message",
    "label": "Ficha técnica sem confirmação",
    "default": "Consultei as opções, mas ainda não consegui confirmar todos os critérios: {criteria}. Posso continuar a busca mantendo essas exigências.",
    "type": "textarea",
    "maxLength": 12000,
    "group": "Qualidade e critérios técnicos",
    "description": "Texto editável no banco; preserve as variáveis indicadas."
  },
  {
    "key": "message.catalog_requirements_no_match",
    "attribute": "catalog_requirements_no_match",
    "target": "message",
    "label": "Opções consultadas incompatíveis",
    "default": "As opções que consultei não atenderam a todos os critérios: {criteria}. Posso continuar procurando com essas características.",
    "type": "textarea",
    "maxLength": 12000,
    "group": "Qualidade e critérios técnicos",
    "description": "Texto editável no banco; preserve as variáveis indicadas."
  },
  {
    "key": "message.catalog_requirements_intro",
    "attribute": "catalog_requirements_intro",
    "target": "message",
    "label": "Introdução das opções confirmadas",
    "default": "Confirmei estas opções com {criteria}:",
    "type": "textarea",
    "maxLength": 12000,
    "group": "Qualidade e critérios técnicos",
    "description": "Texto editável no banco; preserve as variáveis indicadas."
  },
  {
    "key": "message.catalog_required_budget",
    "attribute": "catalog_required_budget",
    "target": "message",
    "label": "Descrição do orçamento exigido",
    "default": "até R$ {amount}",
    "type": "textarea",
    "maxLength": 12000,
    "group": "Qualidade e critérios técnicos",
    "description": "Texto editável no banco; preserve as variáveis indicadas."
  },
  {
    "key": "message.catalog_requirement_line",
    "attribute": "catalog_requirement_line",
    "target": "message",
    "label": "Descrição de característica confirmada",
    "default": "{label}",
    "type": "textarea",
    "maxLength": 12000,
    "group": "Qualidade e critérios técnicos",
    "description": "Texto editável no banco; preserve as variáveis indicadas."
  },
  {
    "key": "message.catalog_selection_missing",
    "attribute": "catalog_selection_missing",
    "target": "message",
    "label": "Escolha sem opções efetivamente apresentadas",
    "default": "Ainda não apresentei uma opção confirmada com os seus critérios. Vou retomar essa busca antes de avançar.",
    "type": "textarea",
    "maxLength": 12000,
    "group": "Qualidade e critérios técnicos",
    "description": "Texto editável no banco; preserve as variáveis indicadas."
  },
  {
    "key": "message.catalog_rerank_system",
    "attribute": "catalog_rerank_system",
    "target": "message",
    "label": "Instrução para ordenar candidatos",
    "default": "Ordene os produtos de CANDIDATES conforme PREFERENCES. Retorne até {limit} IDs que constem em ALLOWED_PRODUCT_IDS. Use exclusivamente as características documentadas dos candidatos. Respeite todas as exigências técnicas e o orçamento; não altere fatos nem invente IDs.",
    "type": "textarea",
    "maxLength": 12000,
    "group": "Qualidade e critérios técnicos",
    "description": "Texto editável no banco; preserve as variáveis indicadas."
  },
  {
    "key": "message.critique_system",
    "attribute": "critique_system",
    "target": "message",
    "label": "Instrução da revisão de resposta",
    "default": "Você é o JUÍZ redundante do agente NewStore. Valide se a resposta cumpre o pedido do cliente com o histórico completo e as capacidades/APIs disponíveis. pass_check=false se a resposta negar pedido/link/pagamento existentes no histórico, inventar fatos, ignorar contexto, ou deixar de consultar API necessária. Também reprove (pass_check=false) quando o cliente pediu um tipo, função ou atributo de produto (ex.: cronógrafo, diver, GMT, automático, cor, orçamento, gênero, marca) e os itens em commercial_data.products / a resposta NÃO evidenciam esse requisito nos nomes ou fatos disponíveis — mesmo que sejam produtos reais da categoria genérica. Nesses casos, recommended_apis DEVE incluir search_products com arguments.query refinada em termos de catálogo (português quando fizer sentido, ex.: 'cronógrafo', 'mergulho', 'GMT'), sem inventar produtos. Quando reprovar, liste recommended_apis (somente retryable) com arguments concretos e retry_instruction objetiva. Não reescreva a resposta final aqui.",
    "type": "textarea",
    "maxLength": 12000,
    "group": "Qualidade e critérios técnicos",
    "description": "Texto editável no banco; preserve as variáveis indicadas."
  },
  {
    "key": "agent_max_llm_calls_per_turn",
    "attribute": "agent_max_llm_calls_per_turn",
    "target": "setting",
    "label": "Agent max llm calls per turn",
    "description": "Parâmetro AGENT_MAX_LLM_CALLS_PER_TURN. Aplicado na próxima conversa após publicação.",
    "group": "Motor e limites",
    "type": "integer",
    "default": 3,
    "readOnly": false,
    "min": 0
  }
]
$quality_catalog$::jsonb) entry
ON CONFLICT (key) DO UPDATE SET definition = EXCLUDED.definition, updated_at = now();
COMMIT;
