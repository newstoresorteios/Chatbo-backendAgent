BEGIN;
INSERT INTO public.agent_configuration_catalog(key,definition,updated_at)
SELECT entry->>'key',entry,now() FROM jsonb_array_elements($catalog$
[
  {
    "key": "readyToShipCategoryIds",
    "target": "policy",
    "type": "textarea",
    "label": "Categorias de pronta entrega",
    "group": "Continuidade e disponibilidade",
    "description": "IDs das categorias oficiais que identificam pronta entrega, separados por vírgula.",
    "maxLength": 12000,
    "default": "403"
  },
  {
    "key": "catalogAvailabilityRules",
    "target": "policy",
    "type": "textarea",
    "label": "Exigência de pronta entrega",
    "group": "Continuidade e disponibilidade",
    "description": "JSON para preservar e retirar a exigência do cliente de pronta entrega.",
    "maxLength": 12000,
    "default": "{\"require\": \"\\\\b(?:a pronta entrega|somente pronta entrega|so pronta entrega|preciso.{0,25}pronta entrega)\\\\b\", \"release\": \"\\\\b(?:pode ser|aceito|pode vir).{0,25}(?:encomenda|sem pressa)\\\\b\", \"historyTurns\": 12}"
  },
  {
    "key": "catalogHistoryRecoveryRules",
    "target": "policy",
    "type": "textarea",
    "label": "Recuperar produto mencionado",
    "group": "Continuidade e disponibilidade",
    "description": "Recupera uma única referência no histórico e confirma no catálogo antes de responder. Não executa compra.",
    "maxLength": 12000,
    "default": "{\"followup\": \"\\\\b(?:foto|fotos|imagem|imagens|link|esse que.{0,15}sugeriu|desse|dele|dessa|dela)\\\\b\", \"reference\": \"\\\\b((?=[A-Z0-9.\\\\-]*\\\\d)(?=[A-Z0-9.\\\\-]*[A-Z])[A-Z0-9]{2,}(?:[-.][A-Z0-9]+)*)\\\\b\", \"historyTurns\": 20}"
  },
  {
    "key": "message.catalog_ready_unconfirmed",
    "target": "message",
    "type": "textarea",
    "label": "Modelo sem pronta entrega confirmada",
    "group": "Continuidade e disponibilidade",
    "description": "Explica quando o modelo existe mas não atende à pronta entrega solicitada.",
    "maxLength": 12000,
    "default": "Localizei {name}, mas não confirmei pronta entrega para esse modelo. A ficha informa: {availability}. Link oficial: {url}"
  },
  {
    "key": "message.catalog_ready_unknown_note",
    "target": "message",
    "type": "textarea",
    "label": "Disponibilidade não informada",
    "group": "Continuidade e disponibilidade",
    "description": "Texto quando a ficha não informa disponibilidade.",
    "maxLength": 12000,
    "default": "disponibilidade não informada"
  }
]
$catalog$::jsonb) entry
ON CONFLICT(key) DO UPDATE SET definition=EXCLUDED.definition,updated_at=now();
COMMIT;
