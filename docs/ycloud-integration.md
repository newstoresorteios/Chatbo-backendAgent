# ChatBô + YCloud: ativação do número piloto

Esta implementação local conecta **um número YCloud por ambiente** à Central de Atendimento existente. O número piloto foi confirmado pela API da YCloud; o número principal não é ativado automaticamente.

## Piloto confirmado na YCloud

Uma consulta de leitura à API da YCloud confirmou estes dados em 23/10/2026:

| Campo | Valor |
| --- | --- |
| Número E.164 | `+554396676633` |
| WABA ID | `2253102025094670` |
| Phone Number ID | `1312419621949456` |
| Status | `CONNECTED` |

Use **exatamente** o número retornado pela YCloud, mesmo que ele tenha oito dígitos após o DDD. A chave de API enviada na conversa deve ser substituída por uma nova chave antes de configurar o Render. Não grave a chave nem o segredo do webhook neste repositório.

## Ativação manual no ambiente publicado

O backend publicado em `https://chatbo-backendagent.onrender.com` ainda não expunha `/api/ycloud/status` na verificação de 23/10/2026. Ele usa o projeto Supabase `fbogrbrkyorjvojeypie`; uma conexão Supabase diferente disponível ao Codex não tem acesso a esse projeto. Assim, a migration e as configurações de produção devem ser feitas no projeto correto.

1. No Supabase do projeto `fbogrbrkyorjvojeypie`, confirme que as migrations anteriores do repositório foram aplicadas. Execute o conteúdo de `supabase/migrations/20261023134658_ycloud_channel_handoff.sql` no SQL Editor desse projeto e confira que terminou sem erro. Não execute no projeto `prompt-atlas`.
2. Publique as alterações locais dos dois repositórios (`Chatbo-backendAgent` e `Chatbo-frontendAgent`) pelo fluxo Git/deploy que já usa para o ChatBô. O Render está com `autoDeploy: true`; confira após a publicação que `/api/ycloud/status` aparece em `https://chatbo-backendagent.onrender.com/openapi.json`. Faça isso antes de criar o webhook para evitar entregas em uma rota inexistente.
3. No serviço Render `chatbo-backendagent`, configure as variáveis abaixo em **Environment**. Use uma chave de API nova, com acesso ao piloto, em `YCLOUD_API_KEY`. Salve e aguarde o redeploy/restart.
4. Na YCloud, abra **Developer → Webhooks → Add Endpoints**, informe `https://chatbo-backendagent.onrender.com/webhooks/ycloud`, e selecione apenas `whatsapp.inbound_message.received` e `whatsapp.message.updated` para este endpoint. Copie o `secret` de assinatura retornado pela YCloud e salve-o no Render como `YCLOUD_WEBHOOK_SECRET`; aguarde o restart. A YCloud envia eventos de todas as WABAs da conta a endpoints globais; o backend filtra pelo WABA e número configurados.
5. No workspace correto do ChatBô, acesse **Canais → WhatsApp via YCloud → Validar e conectar YCloud**. Só então o canal piloto é ativado. Confira número e provedor no painel antes de mandar a primeira mensagem de teste.
6. Mande uma mensagem de outro celular para o piloto. Consulte **Developer → Webhooks → delivery logs** na YCloud e confirme HTTP 200; confira a conversa e a resposta no ChatBô. Use os testes manuais por etapa mais abaixo para validar bot e handoff.

Para o Render, use estes valores não secretos:

```dotenv
YCLOUD_PHONE_NUMBER=+554396676633
YCLOUD_WABA_ID=2253102025094670
YCLOUD_PHONE_NUMBER_ID=1312419621949456
PUBLIC_API_URL=https://chatbo-backendagent.onrender.com
```

Adicione `YCLOUD_API_KEY` e `YCLOUD_WEBHOOK_SECRET` diretamente no painel do Render, sem copiá-los para arquivos versionados. O endpoint de webhook criado na YCloud fornece o segredo; não invente um valor diferente.

## 1. Preparação

No backend, configure estas variáveis no ambiente do servidor (sem colocá-las no frontend ou no Git):

| Variável | Uso |
| --- | --- |
| `YCLOUD_API_KEY` | Chave da API YCloud usada para validar e enviar. |
| `YCLOUD_WEBHOOK_SECRET` | Segredo usado para verificar `YCloud-Signature`; é obrigatório para ativar. |
| `YCLOUD_PHONE_NUMBER` | Número piloto exato, em E.164, por exemplo `+55...`; confirme no painel YCloud. |
| `YCLOUD_WABA_ID` | WABA ID ao qual o piloto pertence. |
| `YCLOUD_PHONE_NUMBER_ID` | Opcional; se informado, deve corresponder ao ID retornado pela YCloud. |
| `PUBLIC_API_URL` | URL pública HTTPS do backend, sem `/api`; o painel mostra a URL do webhook. |

As variáveis existentes de Supabase, autenticação e IA continuam necessárias para o ChatBô. A API key e o segredo **não são salvos** em `canais`; apenas IDs e telefone do canal são persistidos. Reinicie o backend depois de alterar o ambiente.

Aplique a migration [`20261023134658_ycloud_channel_handoff.sql`](../supabase/migrations/20261023134658_ycloud_channel_handoff.sql) ao banco usado pelo backend. Ela acrescenta `provider` e `last_customer_message_at` a `conversas`, garante unicidade do canal piloto, cria funções de gravação atômica e reconciliação de status, e permite que a Central mostre `bot_unavailable` como aguardando humano. A migration depende das tabelas e índices já existentes do projeto; não foi aplicada em banco remoto durante esta entrega.

## 2. Cadastro e webhook

1. Cadastre o piloto na YCloud e confirme no painel da YCloud o número completo, WABA ID e status `CONNECTED`.
2. Configure as variáveis acima no backend e reinicie-o.
3. Na YCloud, crie um webhook HTTPS para `https://SEU_BACKEND/webhooks/ycloud`. Ative `whatsapp.inbound_message.received` e `whatsapp.message.updated`. Copie o segredo retornado pela YCloud para `YCLOUD_WEBHOOK_SECRET` no backend.
4. Entre no workspace certo do ChatBô, abra **Canais → WhatsApp via YCloud** e clique **Validar e conectar YCloud**. A ação consulta a YCloud e só ativa o canal após conferir número, WABA, status e ID opcional.
5. Confira o canal com `provider=ycloud`, número e estado conectado. O endpoint autenticado `GET /api/ycloud/status` também mostra o estado, sem devolver credenciais.

O webhook rejeita assinatura ausente/inválida ou com timestamp fora de cinco minutos, antes de interpretar o JSON. Eventos de outros números/WABAs são ignorados. Mensagens são deduplicadas pelo ID externo `ycloud:<id>`. A função SQL grava mensagem, contador de não lidas e horário da janela na mesma transação. Status recebidos antes de o ID de saída ser gravado ficam temporariamente em `ycloud_pending_statuses` e são conciliados na associação do ID.

## 3. Testes manuais por etapa

**Cadastro + webhook:** com as credenciais do piloto, valide o canal no painel. Confira `GET /api/ycloud/status`. Envie uma mensagem de outro celular ao piloto. Veja o webhook responder 200 e a conversa aparecer apenas no workspace conectado. Reenvie o mesmo evento: não deve surgir outra mensagem nem outra resposta do bot. Assinatura inválida deve retornar 401.

**Persistência:** abra a Central de Atendimento. Confira o contato, a mensagem recebida, o horário e o indicador de não lidas. Envie mensagens a partir de dois contatos e confira os dois históricos. Se o mesmo contato já conversa por outro número, os históricos devem continuar separados por `canal_id`. Envie resposta e confira as mudanças de status `sent`, `delivered`, `read` ou `failed` conforme chegarem eventos YCloud.

**Painel + automação:** com um fluxo WhatsApp ativo e o serviço de IA configurado, envie uma mensagem nova ao piloto. O bot deve responder pelo próprio número e o histórico deve mostrar `sender=ai`. Confira que a lista e o histórico se atualizam pelos eventos existentes da Central. Se não houver resposta/fluxo, a conversa deve passar para **Aguardando humano**. Mensagens recebidas antes da ativação do webhook não são importadas automaticamente.

**Handoff:** peça “quero falar com atendente”; o bot deve parar só naquela conversa e o painel deve mostrar **Aguardando humano**. Clique **Assumir**, envie uma resposta e confira `sender=agent` e o envio pelo piloto. Clique **Devolver ao bot**; envie outra mensagem de cliente e confira que o bot voltou. Verifique em paralelo que conversas de outros números continuam no estado anterior. Se a IA indicar que não sabe responder, a conversa também deve solicitar humano.

**Janela de 24h:** use uma conversa cuja última mensagem do cliente tenha mais de 24 horas. O painel deve avisar e bloquear texto livre; uma tentativa direta à API deve retornar HTTP 409. O envio de template aprovado ainda não está implementado nesta etapa, portanto não há ação disponível no painel para reabrir essa conversa fora da janela.

## 4. Validação local

No backend: `python -m pytest -q` e `python -m compileall -q app`.

No frontend: `npm ci`, `npm test -- --run` e `npm run build`. O lint global pode apontar um erro preexistente em `src/hooks/useConversationAgentContext.test.ts`; para validar somente os arquivos alterados, use `npx eslint` com os caminhos editados.

## Limites atuais

- A integração real depende do número piloto registrado na YCloud, das credenciais, da migration no banco usado pela aplicação e de um webhook HTTPS acessível. Testes locais não confirmam operação de produção.
- Mídias recebidas aparecem como mensagem descritiva no histórico; o arquivo de mídia não é baixado. Envio de anexos e templates YCloud ainda não estão disponíveis.
- Um ambiente de backend usa um conjunto de credenciais YCloud e um número piloto. Para adicionar o número principal depois, planeje configuração por canal/segredo antes de ativar um segundo número no mesmo ambiente.

## Histórico de números em coexistência

Para números conectados à YCloud em modo de coexistência com o app WhatsApp Business, a YCloud envia o histórico pelo evento `whatsapp.smb.history`.

1. Aplique `supabase/migrations/20261023170000_ycloud_history_import.sql` no mesmo projeto Supabase.
2. Na YCloud, adicione `whatsapp.smb.history` aos eventos do endpoint `https://SEU_BACKEND/webhooks/ycloud`.
3. As mensagens são gravadas por contato: recebidas como `customer`, enviadas pelo app como `agent`. Duplicatas são ignoradas pelo ID externo.
4. O histórico não gera contagem de não lidas, resposta do bot nem pedido de atendimento. Conversas criadas apenas pelo histórico ficam como encerradas; uma nova mensagem do cliente as reabre.
5. A Meta dispara o envio do histórico no momento da conexão do número. A YCloud não oferece consulta sob demanda de mensagens WhatsApp. Um backend atende um único número; para importar o histórico do número principal, o ambiente precisa estar configurado com ele.
