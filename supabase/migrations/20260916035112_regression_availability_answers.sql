BEGIN;
INSERT INTO public.agent_configuration_catalog(key,definition,updated_at)
SELECT entry->>'key',entry,now() FROM jsonb_array_elements($catalog$
[
  {
    "key": "catalogAvailabilityRules",
    "target": "policy",
    "type": "textarea",
    "label": "Exigência de pronta entrega",
    "group": "Continuidade e disponibilidade",
    "description": "JSON para preservar e retirar a exigência do cliente de pronta entrega.",
    "maxLength": 12000,
    "default": "{\"require\": \"\\\\b(?:a pronta entrega|somente pronta entrega|so pronta entrega|preciso.{0,25}pronta entrega)\\\\b\", \"release\": \"\\\\b(?:pode ser|aceito|pode vir).{0,25}(?:encomenda|sem pressa)\\\\b\", \"historyTurns\": 12, \"question\": \"\\\\b(?:qual.{0,20}prazo|prazo de entrega|pronta entrega ou|sob encomenda|quanto tempo.{0,20}(?:chega|entrega))\\\\b\"}"
  },
  {
    "key": "message.catalog_ready_no_match",
    "target": "message",
    "type": "textarea",
    "label": "Sem pronta entrega confirmada na busca",
    "group": "Continuidade e disponibilidade",
    "description": "Usada após consulta sem resultado elegível; não afirma ausência definitiva no catálogo.",
    "maxLength": 12000,
    "default": "Não confirmei uma opção com pronta entrega que atenda aos critérios na consulta atual. Posso verificar opções sob encomenda, se esse prazo servir para você."
  },
  {
    "key": "message.catalog_availability_item",
    "target": "message",
    "type": "textarea",
    "label": "Prazo da ficha do produto",
    "group": "Continuidade e disponibilidade",
    "description": "Resume a informação da ficha sem confundir disponibilidade ou despacho com entrega garantida.",
    "maxLength": 12000,
    "default": "{name}: {availability}. O prazo final para seu endereço deve ser confirmado no checkout. {url}"
  }
]
$catalog$::jsonb) entry
ON CONFLICT(key) DO UPDATE SET definition=EXCLUDED.definition,updated_at=now();
COMMIT;
