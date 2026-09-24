# Atualização da Central por eventos

O backend assina Supabase Postgres Changes nas tabelas `ai_inbound_messages`,
`ai_agent_responses`, `conversas` e `mensagens`. Eventos AI sincronizam apenas a
thread afetada, incluindo mensagens, antes de invalidar caches e avisar a tela.
O NSAgent e suas regras de conversa/ManyChat não são alterados.

A tela usa `GET /api/conversas/events?cursor=...`, com o Bearer habitual, em long
poll de até 20 segundos. Isso **não** adiciona 20 segundos de atraso: a resposta
é liberada assim que chega o evento. O endpoint resolve a empresa no servidor;
retorna somente cursor, changed e realtime, nunca conteúdo ou chaves Supabase.
Cada nova espera revalida autenticação. A aba oculta cancela a conexão. Logout,
mudança de empresa e desmontagem encerram o consumidor. Falhas reconectam após
3 segundos; o polling existente permanece ativo durante toda a implantação.

## Publicação e verificação

1. Revisar RLS/grants das quatro tabelas e executar advisors antes de aplicar
   `20260924204412_inbox_realtime_events.sql`. A migração só inclui tabelas na
   publication existente, sem conceder acesso a anon/authenticated.
2. Publicar backend e frontend. Nenhuma credencial nova no frontend. O backend
   usa SUPABASE_URL/SUPABASE_KEY existentes (credencial exclusivamente servidor).
3. Em sessão autenticada, confirmar `realtime: true` no endpoint de eventos.
4. Enviar mensagem de teste no Instagram e medir chegada, gravação/sincronização
   e renderização na Central. Validar entrada, resposta AI, troca de conversa,
   retomada após aba oculta e duas empresas diferentes.
5. Desconectar Realtime e confirmar que a atualização por polling continua.

Meta de latência: reduzir espera de polling; subsegundo ainda depende da
materialização e das consultas REST e deve ser medido após deploy. Não é uma
garantia, nem reduz o tempo de geração OpenAI. O cursor é local ao processo;
esta versão é para o Render atual, de uma instância/processo. Para múltiplos
workers/instâncias, usar revisões compartilhadas antes de escalar.

Não registrar payloads de eventos nem URLs autenticadas. Monitorar aviso de fila
cheia/Realtime indisponível. A fila é limitada; perdas são recuperadas pelo
polling. DELETE sem workspace não é distribuído e depende dessa reconciliação.

Documentação consultada: https://supabase.com/docs/guides/realtime/postgres-changes
