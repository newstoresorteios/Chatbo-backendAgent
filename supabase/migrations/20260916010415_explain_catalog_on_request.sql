BEGIN;
INSERT INTO public.agent_configuration_catalog(key,definition,updated_at)
SELECT entry->>'key',entry,now() FROM jsonb_array_elements($on_request$
[
  {
    "key": "message.catalog_requirements_price_on_request",
    "target": "message",
    "type": "textarea",
    "label": "Características confirmadas com preço sob consulta",
    "group": "Qualidade e critérios técnicos",
    "description": "Resultado parcial de uma ficha tecnicamente compatível, com upon_request confirmado e preço ausente ou zero. Variáveis: product, criteria.",
    "maxLength": 3000,
    "default": "Encontrei o {product}, que confirma as características técnicas pedidas, mas está com disponibilidade sob consulta e sem preço válido na ficha. Assim, ainda não consigo confirmar uma opção para {criteria}."
  }
]
$on_request$::jsonb) entry
ON CONFLICT(key) DO UPDATE SET definition=EXCLUDED.definition,updated_at=now();
COMMIT;
