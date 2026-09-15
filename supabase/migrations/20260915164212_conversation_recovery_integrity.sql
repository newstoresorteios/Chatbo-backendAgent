-- Preserve merged sessions and message relocation history; do not delete transcripts.
ALTER TABLE public.conversas ADD COLUMN IF NOT EXISTS merged_into uuid REFERENCES public.conversas(id);
ALTER TABLE public.conversas ADD CONSTRAINT conversas_not_merged_into_self CHECK (merged_into IS DISTINCT FROM id);

CREATE TABLE public.conversation_reconciliation_audit (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workspace_id uuid NOT NULL REFERENCES public.workspaces(id),
    entity_type text NOT NULL CHECK (entity_type IN ('conversation','message')),
    entity_id uuid NOT NULL,
    destination_id uuid NOT NULL,
    original_row jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.conversation_reconciliation_audit ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.conversation_reconciliation_audit FROM PUBLIC, anon, authenticated;
GRANT SELECT,INSERT ON public.conversation_reconciliation_audit TO service_role;
GRANT USAGE,SELECT ON SEQUENCE public.conversation_reconciliation_audit_id_seq TO service_role;

-- Use only unambiguous, already established ownership to repair legacy rows.
WITH owners AS (
    SELECT external_thread_id, channel, min(workspace_id::text)::uuid AS workspace_id
    FROM public.conversas WHERE workspace_id IS NOT NULL AND external_thread_id IS NOT NULL
    GROUP BY external_thread_id, channel HAVING count(DISTINCT workspace_id)=1
)
UPDATE public.ai_inbound_messages i SET workspace_id=o.workspace_id
FROM owners o WHERE i.workspace_id IS NULL AND i.conversation_id=o.external_thread_id AND i.channel=o.channel;

UPDATE public.ai_agent_responses r SET workspace_id=i.workspace_id
FROM public.ai_inbound_messages i WHERE r.inbound_id=i.id AND r.workspace_id IS NULL AND i.workspace_id IS NOT NULL;

WITH owners AS (
    SELECT inbound_id,min(workspace_id::text)::uuid AS workspace_id
    FROM public.ai_agent_responses WHERE workspace_id IS NOT NULL AND inbound_id IS NOT NULL
    GROUP BY inbound_id HAVING count(DISTINCT workspace_id)=1
)
UPDATE public.ai_inbound_messages i SET workspace_id=o.workspace_id
FROM owners o WHERE i.id=o.inbound_id AND i.workspace_id IS NULL;

CREATE OR REPLACE FUNCTION public.stamp_agent_inbound_workspace()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
    IF NEW.workspace_id IS NOT NULL AND NEW.inbound_id IS NOT NULL THEN
        IF EXISTS (SELECT 1 FROM public.ai_inbound_messages i WHERE i.id=NEW.inbound_id
                   AND i.workspace_id IS NOT NULL AND i.workspace_id<>NEW.workspace_id) THEN
            RAISE EXCEPTION 'agent_response_workspace_mismatch';
        END IF;
        UPDATE public.ai_inbound_messages SET workspace_id=NEW.workspace_id
        WHERE id=NEW.inbound_id AND workspace_id IS NULL;
    END IF;
    RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.stamp_agent_inbound_workspace() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.stamp_agent_inbound_workspace() TO service_role;
CREATE TRIGGER ai_response_stamp_workspace AFTER INSERT OR UPDATE OF workspace_id
ON public.ai_agent_responses FOR EACH ROW EXECUTE FUNCTION public.stamp_agent_inbound_workspace();

-- Serialize reconciliation and the unique-index installation against writers.
LOCK TABLE public.conversas IN SHARE ROW EXCLUSIVE MODE;
CREATE TEMP TABLE session_merge_map ON COMMIT DROP AS
WITH ranked AS (
    SELECT c.id, c.workspace_id,
        first_value(c.id) OVER (PARTITION BY c.workspace_id,c.channel,coalesce(c.canal_id,''),c.external_thread_id
            ORDER BY (nullif(c.assigned_to,'') IS NOT NULL) DESC,(c.bot_activated IS FALSE) DESC,
                (SELECT count(*) FROM public.mensagens m WHERE m.conversa_id=c.id) DESC,c.created_at,c.id) AS canonical_id
    FROM public.conversas c WHERE c.workspace_id IS NOT NULL AND c.channel IS NOT NULL
        AND nullif(btrim(c.external_thread_id),'') IS NOT NULL AND c.merged_into IS NULL
)
SELECT * FROM ranked WHERE id<>canonical_id;

INSERT INTO public.conversation_reconciliation_audit(workspace_id,entity_type,entity_id,destination_id,original_row)
SELECT x.workspace_id,'conversation',c.id,x.canonical_id,to_jsonb(c)
FROM session_merge_map x JOIN public.conversas c ON c.id=x.id;

INSERT INTO public.conversation_reconciliation_audit(workspace_id,entity_type,entity_id,destination_id,original_row)
SELECT x.workspace_id,'message',m.id,x.canonical_id,to_jsonb(m)
FROM session_merge_map x JOIN public.mensagens m ON m.conversa_id=x.id;

UPDATE public.mensagens m SET conversa_id=x.canonical_id FROM session_merge_map x WHERE m.conversa_id=x.id;
UPDATE public.conversas c SET merged_into=x.canonical_id,status='closed',assigned_to=NULL,bot_activated=true
FROM session_merge_map x WHERE c.id=x.id;

CREATE UNIQUE INDEX idx_conversas_workspace_session_unique
ON public.conversas(workspace_id,channel,coalesce(canal_id,''),external_thread_id)
WHERE workspace_id IS NOT NULL AND channel IS NOT NULL
  AND nullif(btrim(external_thread_id),'') IS NOT NULL AND merged_into IS NULL;

-- Relocate previously mixed AI messages according to the immutable inbound thread.
CREATE TEMP TABLE message_session_map ON COMMIT DROP AS
WITH sources AS (
    SELECT m.id,m.conversa_id,i.workspace_id,i.conversation_id,i.channel
    FROM public.mensagens m JOIN public.ai_inbound_messages i ON m.external_id='ai-in-'||i.id::text
    UNION ALL
    SELECT m.id,m.conversa_id,i.workspace_id,i.conversation_id,i.channel
    FROM public.mensagens m JOIN public.ai_agent_responses r ON m.external_id='ai-out-'||r.id::text
    JOIN public.ai_inbound_messages i ON i.id=r.inbound_id AND i.workspace_id=r.workspace_id
), targets AS (
    SELECT s.id,s.conversa_id,s.workspace_id,min(c.id::text)::uuid AS destination_id
    FROM sources s JOIN public.conversas c ON c.workspace_id=s.workspace_id
        AND c.external_thread_id=s.conversation_id AND c.channel=s.channel AND c.merged_into IS NULL
    GROUP BY s.id,s.conversa_id,s.workspace_id HAVING count(*)=1
)
SELECT * FROM targets WHERE conversa_id<>destination_id;

INSERT INTO public.conversation_reconciliation_audit(workspace_id,entity_type,entity_id,destination_id,original_row)
SELECT x.workspace_id,'message',m.id,x.destination_id,to_jsonb(m)
FROM message_session_map x JOIN public.mensagens m ON m.id=x.id;
UPDATE public.mensagens m SET conversa_id=x.destination_id,workspace_id=x.workspace_id
FROM message_session_map x WHERE m.id=x.id;

CREATE INDEX IF NOT EXISTS idx_ai_inbound_workspace_thread ON public.ai_inbound_messages(workspace_id,conversation_id,created_at);
CREATE INDEX IF NOT EXISTS idx_ai_response_workspace_inbound ON public.ai_agent_responses(workspace_id,inbound_id,created_at);
CREATE INDEX IF NOT EXISTS idx_catalog_tenant_reference_fold ON public.ai_catalog_index(tenant_id,lower(reference));
NOTIFY pgrst,'reload schema';

-- New controls are defaults only; published operator overrides are preserved.
INSERT INTO public.agent_configuration_catalog(key,definition)
SELECT item->>'key',item FROM jsonb_array_elements($recovery$[{"key": "conversationRepairPhrases", "type": "textarea", "default": "que pergunta de preço\nnão perguntei o preço\nnão pedi preço\nnão foi isso que perguntei\nnão foi isso que pedi\nvocê não entendeu\nvocê entendeu errado\nta entendendo nada\ntá entendendo nada\nnão está entendendo\nnão ta entendendo\nnão tá entendendo", "label": "Expressões de correção e frustração", "maxLength": 6000, "target": "policy", "attribute": "conversationRepairPhrases", "group": "Continuidade e recuperação", "description": "Política versionada aplicada a cada atendimento."}, {"key": "conversationRepairHandoffAfter", "type": "integer", "default": 2, "min": 1, "max": 5, "label": "Reclamações consecutivas antes de encaminhar", "target": "policy", "attribute": "conversationRepairHandoffAfter", "group": "Continuidade e recuperação", "description": "Política versionada aplicada a cada atendimento."}, {"key": "checkoutContextMaxAgeSeconds", "type": "integer", "default": 43200, "min": 300, "max": 604800, "label": "Validade do contexto de carrinho sem pedido (segundos)", "target": "policy", "attribute": "checkoutContextMaxAgeSeconds", "group": "Continuidade e recuperação", "description": "Política versionada aplicada a cada atendimento."}, {"key": "browseContextMaxAgeSeconds", "type": "integer", "default": 43200, "min": 300, "max": 604800, "label": "Validade da seleção de produtos (segundos)", "target": "policy", "attribute": "browseContextMaxAgeSeconds", "group": "Continuidade e recuperação", "description": "Política versionada aplicada a cada atendimento."}, {"key": "message.double_check_system", "target": "message", "attribute": "double_check_system", "label": "Instrução da revisão independente", "default": "Você é um juiz independente do agente de vendas. Não reescreva a resposta. Não sugira APIs. action=approve se a reply responde o pedido com os fatos listados. action=veto se inventou preço, link ou SKU, ignorou PIX/pedido existente, ou não atendeu o pedido. action=handoff só se pagamento ou pedido foi afirmado sem evidência. code deve ser pix, price, order, sku ou unanswered. Diferencie uma reclamação sobre a resposta anterior de uma solicitação comercial. requested_subject descreve o desejo do cliente, não um produto confirmado no catálogo: repetir esse desejo para reconhecer uma correção não afirma estoque, preço ou existência. Somente products e os campos de pedido/pagamento fornecidos sustentam fatos comerciais.", "group": "Continuidade e recuperação", "description": "Mensagem ou instrução de atendimento editável e versionada.", "type": "textarea", "maxLength": 6000, "variables": []}, {"key": "message.double_check_insufficiency", "target": "message", "attribute": "double_check_insufficiency", "label": "Resposta quando faltam evidências", "default": "Não consigo confirmar isso com segurança agora. Posso verificar de novo ou te passar para um atendente.", "group": "Continuidade e recuperação", "description": "Mensagem ou instrução de atendimento editável e versionada.", "type": "textarea", "maxLength": 6000, "variables": []}, {"key": "message.conversation_repair_ack", "target": "message", "attribute": "conversation_repair_ack", "label": "Reconhecimento de erro na interpretação", "default": "Você tem razão, interpretei seu pedido errado. Vou retomar os critérios que você informou.", "group": "Continuidade e recuperação", "description": "Mensagem ou instrução de atendimento editável e versionada.", "type": "textarea", "maxLength": 6000, "variables": []}, {"key": "message.conversation_repair_handoff", "target": "message", "attribute": "conversation_repair_handoff", "label": "Encaminhamento após falha de compreensão", "default": "Desculpe pela confusão. Vou solicitar ajuda da equipe para continuar seu atendimento com as informações que você já passou.", "group": "Continuidade e recuperação", "description": "Mensagem ou instrução de atendimento editável e versionada.", "type": "textarea", "maxLength": 6000, "variables": []}, {"key": "message.conversation_repair_missing_context", "target": "message", "attribute": "conversation_repair_missing_context", "label": "Correção sem contexto suficiente", "default": "Desculpe, interpretei errado. Qual ponto da resposta você quer que eu corrija?", "group": "Continuidade e recuperação", "description": "Mensagem ou instrução de atendimento editável e versionada.", "type": "textarea", "maxLength": 6000, "variables": []}, {"key": "catalogWarmBrands", "type": "textarea", "default": "Orient\nSeiko\nCitizen\nTissot\nBulova\nCasio\nLongines\nCertina\nTAG Heuer\nHamilton", "label": "Marcas a incluir na atualização do índice", "maxLength": 6000, "target": "policy", "attribute": "catalogWarmBrands", "group": "Continuidade e recuperação", "description": "Política versionada aplicada a cada atendimento."}, {"key": "catalogWarmBrandLimit", "type": "integer", "default": 8, "min": 1, "max": 25, "label": "Marcas por execução de atualização", "target": "policy", "attribute": "catalogWarmBrandLimit", "group": "Continuidade e recuperação", "description": "Política versionada aplicada a cada atendimento."}, {"key": "catalogWarmProductsPerBrand", "type": "integer", "default": 80, "min": 5, "max": 200, "label": "Produtos por marca na atualização", "target": "policy", "attribute": "catalogWarmProductsPerBrand", "group": "Continuidade e recuperação", "description": "Política versionada aplicada a cada atendimento."}, {"key": "catalogStaleDays", "type": "integer", "default": 3, "min": 1, "max": 30, "label": "Dias para sinalizar dados antigos no catálogo", "target": "policy", "attribute": "catalogStaleDays", "group": "Continuidade e recuperação", "description": "Política versionada aplicada a cada atendimento."}]$recovery$::jsonb) item
ON CONFLICT(key) DO NOTHING;
