BEGIN;

INSERT INTO public.agent_configuration_catalog(key, definition, updated_at)
SELECT entry->>'key', entry, now()
FROM jsonb_array_elements($catalog$
[
  {
    "key": "trustedInboundMediaHosts",
    "target": "policy",
    "type": "textarea",
    "label": "Domínios confiáveis para mídia recebida",
    "group": "Interpretação de imagens",
    "description": "Lista JSON de domínios HTTPS autorizados para baixar imagens e áudios recebidos. A validação de DNS público, tamanho e tipo do arquivo continua obrigatória.",
    "maxLength": 4000,
    "default": "[\"storage.googleapis.com\"]"
  },
  {
    "key": "inboundBurstWindowMs",
    "target": "policy",
    "type": "integer",
    "label": "Janela para agrupar mensagens",
    "group": "Conversas",
    "description": "Tempo em milissegundos para reunir mensagens consecutivas do mesmo contato em um único turno e uma única resposta.",
    "min": 0,
    "max": 15000,
    "step": 250,
    "default": 2500
  },
  {
    "key": "inboundBurstMaxMessages",
    "target": "policy",
    "type": "integer",
    "label": "Máximo de mensagens por grupo",
    "group": "Conversas",
    "description": "Quantidade máxima de mensagens consecutivas reunidas no mesmo turno.",
    "min": 1,
    "max": 25,
    "step": 1,
    "default": 8
  }
]
$catalog$::jsonb) entry
ON CONFLICT(key) DO UPDATE
SET definition = EXCLUDED.definition,
    updated_at = now();

COMMIT;
