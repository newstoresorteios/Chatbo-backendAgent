BEGIN;
INSERT INTO public.agent_configuration_catalog(key,definition,updated_at)
SELECT entry->>'key',entry,now() FROM jsonb_array_elements($product_benefits$
[
  {
    "key": "message.catalog_retrieval_response_contract",
    "target": "message",
    "type": "textarea",
    "label": "Resposta após consultar o catálogo",
    "group": "Qualidade das respostas",
    "description": "Como transformar o resultado da consulta em resposta ao cliente.",
    "maxLength": 6000,
    "default": "RETRIEVAL_RESULT contém o resultado da consulta já executada e FACTS contém os produtos autorizados. Responda ao pedido usando esse resultado. Não diga que ainda vai buscar ou peça autorização para uma busca já solicitada e executada. Uma lista vazia com status catalog_requirements_unknown significa que a consulta não confirmou a combinação; informe essa limitação, sem afirmar ausência em todo o catálogo. Com catalog_requirements_no_match, explique que as opções consultadas não atenderam aos critérios. Não substitua a conclusão por uma pergunta opcional de estilo. Na pergunta sobre uma característica de um item já listado, consulte esse item e responda se a característica está confirmada, é diferente ou não consta da ficha; não transforme a pergunta em exigência de uma nova recomendação nem em compra. Em technical_evidence, stage live_detail confirma que get_product ja foi consultado. commercial.price_status missing indica que a ficha retornou preco ausente ou zero, nao que faltou consultar. Quando status matched e availability available, informe o modelo tecnicamente compativel e a falta de preco valido; nao recomende por zero, nao confirme o orcamento e nao exija repetir a mesma consulta sem nova evidencia. Em uma pergunta pontual sobre a característica de um produto, responda diretamente com os dados confirmados da ficha. Não acrescente benefícios ou avaliações de manutenção, custo de manutenção, durabilidade, precisão ou confiabilidade daquele modelo sem uma fonte explícita. Não deduza facilidade de manutenção do tipo de movimento ou do calibre. Só acrescente uma explicação técnica geral quando solicitada, deixando claro que é geral e não uma garantia daquele produto."
  },
  {
    "key": "message.critique_availability_evidence",
    "target": "message",
    "type": "textarea",
    "label": "Revisão das evidências de disponibilidade",
    "group": "Qualidade das respostas",
    "description": "Complemento da revisão para interpretar campos de estoque, disponibilidade e prazo.",
    "maxLength": 6000,
    "default": "Julgue as afirmações exatas da resposta. Em commercial_data.products, available, available_in_store e available_for_purchase determinam disponibilidade comercial; stock positivo não garante possibilidade de compra. availability é a observação textual da ficha e pode ser citada como observação, mesmo quando a venda está desabilitada. availability_days sozinho não prova dias úteis nem venda sob encomenda. upon_request verdadeiro confirma disponibilidade sob consulta; não deduza isso de um prazo isolado. Não rejeite uma citação fiel de availability como prazo inventado. Não confunda encontrar o modelo no catálogo com afirmar que está disponível para compra. Quando a resposta reconhece a indisponibilidade e cita a ficha sem prometer entrega, não exija consulta duplicada da mesma evidência. retrieval_result descreve uma busca ja realizada. products vazio nao significa que nenhuma consulta ocorreu. Julgue a conclusao conforme technical_evidence e product_resolution_state. Uma resposta que apenas promete buscar novamente, apesar de criterios suficientes e consulta concluida, falha em atender o pedido. Em technical_evidence, stage live_detail confirma que get_product ja foi consultado. commercial.price_status missing indica que a ficha retornou preco ausente ou zero, nao que faltou consultar. Quando status matched e availability available, informe o modelo tecnicamente compativel e a falta de preco valido; nao recomende por zero, nao confirme o orcamento e nao exija repetir a mesma consulta sem nova evidencia. Em uma pergunta pontual sobre a característica de um produto, responda diretamente com os dados confirmados da ficha. Não acrescente benefícios ou avaliações de manutenção, custo de manutenção, durabilidade, precisão ou confiabilidade daquele modelo sem uma fonte explícita. Não deduza facilidade de manutenção do tipo de movimento ou do calibre. Só acrescente uma explicação técnica geral quando solicitada, deixando claro que é geral e não uma garantia daquele produto."
  }
]
$product_benefits$::jsonb) entry
ON CONFLICT(key) DO UPDATE SET definition=EXCLUDED.definition,updated_at=now();
COMMIT;
