# Integração YCloud: número piloto

## Objetivo

Conectar um número WhatsApp cadastrado na YCloud ao ChatBô, usando a Central de Atendimento atual para histórico, bot e handoff. O primeiro número é piloto; a ativação do número principal fica para uma etapa posterior. A identidade do piloto será lida da YCloud e das variáveis de ambiente, sem fixar no código o número digitado na conversa.

## Escopo e limites

- Uma configuração YCloud por ambiente de backend. Credenciais só no ambiente do servidor.
- Nenhuma alteração de credenciais ou constantes dos provedores Meta, Brevo e XNamai existentes.
- O cadastro exige confirmação remota de `status=CONNECTED`, WABA, telefone E.164 e Phone Number ID quando configurado.
- Somente um workspace pode vincular a combinação YCloud, WABA e telefone. Um canal YCloud não pode ser ativado pelo toggle genérico.
- Histórico anterior ao webhook não é importado; download/envio de mídia e templates não fazem parte desta etapa. Mídias recebidas aparecem no histórico como indicação textual.
- A homologação real só ocorrerá após o cadastro do piloto na YCloud, credenciais e webhook HTTPS.

## Arquitetura

Um provider YCloud implementa consulta do número, envio de texto e verificação de assinatura HMAC-SHA256 do corpo bruto com `YCloud-Signature`. O serviço YCloud vincula canal e workspace, processa eventos `whatsapp.inbound_message.received` e `whatsapp.message.updated`, e despacha respostas para o bot existente. Um router separado publica `/api/ycloud/*` e `/webhooks/ycloud`.

O banco mantém uma conversa por `(workspace_id, canal_id, telefone do cliente)` e mensagens por ID externo `ycloud:<id>`. Um índice único impede duplicatas mesmo sob reentrega concorrente. O serviço só atualiza prévia, não lidas e a janela de 24 horas após inserir mensagem nova. O timestamp da última mensagem do cliente nunca retrocede quando eventos chegam fora de ordem.

O envio humano ou da IA seleciona YCloud pelo `provider` do canal da conversa antes de qualquer seleção legada por workspace. O servidor verifica a janela de 24 horas antes de enviar texto livre. O `id` de saída da YCloud é persistido para correlação de status. Falhas de envio permanecem visíveis como falhas, sem indicar entrega.

A Central já agrupa por `canal_id` e oferece atualização por eventos/consultas. O painel mostra estado bot ativo, aguardando humano ou atendimento humano, e a hora limite de texto livre. Assumir pausa o bot apenas na conversa; devolver limpa a atribuição e reativa o bot. Pedido expresso de humano ou incapacidade do bot gera fila de espera. O bot revalida o estado antes de responder, inclusive depois de um handoff.

## Segurança e erros

- Webhook sem segredo configurado: 503; assinatura ausente, inválida ou fora da tolerância temporal: 401; JSON inválido: 400.
- Evento para WABA/número/canal desconhecido não altera dados de outros canais.
- Endpoints de cadastro e devolução usam autenticação, permissão e escopo do workspace.
- O frontend não recebe API key nem segredo. Logs evitam corpo bruto, tokens e telefones completos.
- Texto livre com janela vencida: HTTP 409 e aviso no painel.

## Verificação

Testes locais cobrem assinatura, cadastro remoto, isolamento, duplicatas, status, roteamento de saída, bot, handoff, janela e regressões dos canais existentes. Build e testes do frontend cobrem contratos e aviso de janela. O roteiro manual com o piloto valida entrada, resposta, assumir/devolver e estados de entrega; não haverá alegação de operação real antes desse teste.
