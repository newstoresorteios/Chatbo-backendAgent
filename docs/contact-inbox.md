# Histórico por contato na Central

O front solicita `scope=contact` nas rotas de conversas. Chamadas sem esse parâmetro mantêm o contrato por sessão usado pelas integrações.

## Publicação

1. Aplicar `supabase/migrations/20260915180040_contact_conversation_inbox.sql` pelo fluxo normal de migrações.
2. Publicar o backend com o suporte a `scope=contact`.
3. Publicar o frontend.

A migração cria somente uma view de leitura. Não move, apaga nem funde registros de conversas ou mensagens. Requer a migração anterior que adicionou `merged_into`. O acesso é restrito ao backend (`service_role`); a view usa `security_invoker` e as consultas exigem o workspace resolvido pelo servidor.

## Identidade e ações

- Agrupamento por workspace, canal, conexão do canal e identidade do contato. Telefones de WhatsApp/SMS são comparados sem pontuação; outros identificadores permanecem exatos. Nomes iguais ou ausência de identidade não unem pessoas.
- O identificador da primeira sessão mantém a janela estável; `sessionIds` permite resolver links para qualquer sessão do histórico.
- A sessão aberta mais recente recebe respostas e anexos. Esperas antigas continuam representadas na fila. A atribuição do contato só é exibida quando todas as sessões abertas têm o mesmo responsável.
- Assumir/transferir atualiza as sessões abertas em uma operação e pausa as identidades do agente. Concluir encerra as sessões abertas. As sessões encerradas continuam no histórico.
- As mensagens são buscadas em todas as sessões do grupo, com paginação global por data e identificador. Mensagens legadas sem workspace são aceitas apenas se ligadas aos IDs de sessões previamente validados para a empresa.

## Verificação local

`python -m pytest tests/test_contact_inbox.py tests/test_conversation_session_integrity.py tests/test_ai_conversas_bridge.py tests/test_conversation_pagination.py tests/test_conversation_read.py -q`

`node scripts/test-contact-inbox.mjs <URL-do-modulo-pglite>` executa a migração em Postgres isolado (PGlite 0.5.8), conferindo agrupamento, histórico, propriedade, ações e permissões. Não acessa produção.
