# Clientes da Tray no Chatbo

A busca lê `clientes` no Supabase. A importação usa a integração Tray da empresa,
sem depender do BI. A identidade é `(workspace_id, tray_id)`, separada do Mercos.
Uma nova execução atualiza o mesmo cadastro; campos omitidos não apagam contatos.
Campos presentes e vazios no detalhe da Tray removem os valores antigos.

O backend inicia uma rotina contínua no lifespan do FastAPI. Primeiro importa
todas as páginas do catálogo e depois completa os telefones pelo detalhe. Cada
progresso fica em `tray_customer_sync_state`; uma lease atômica por empresa evita
duas instâncias executando o mesmo lote. Reinícios retomam o progresso salvo.
Mesmo durante a importação dos telefones, alterações são consultadas a cada
15 minutos por `modified` (com cobertura da virada de data em São Paulo).
Uma varredura completa diária reconcilia os cadastros. A cota diária da Tray
pode fazer a carga inicial dos telefones durar vários dias; a rotina retoma
automaticamente. Ela não aumenta a cota nem modifica o plano da Tray.

`POST /api/tray/clientes/sincronizar`, com autenticação e permissão
`manageIntegrations`, recebe `{"page":1,"limit":50}`. A empresa vem do usuário,
não do corpo da requisição. Continue com `nextPage` até receber `null`.
Em caso de falha, repita a mesma página. A listagem da Tray não traz telefone:
cada cliente é enriquecido pelo endpoint de detalhe antes de salvar a página.

Para importar a base inteira no servidor ou em um computador autorizado:

```powershell
python scripts/sync_tray_customers.py --workspace-id UUID_DA_EMPRESA --checkpoint output/tray-customers-checkpoint.json
```

O script respeita intervalos entre páginas, espera em limites temporários e salva
a próxima página após cada lote concluído. Se atingir a cota diária, encerra e
permite continuar usando o mesmo checkpoint. Não envia mensagens aos clientes.
Execute novamente sem checkpoint para atualizar todos os contatos.

As migrations `tray_customer_sync`, `automatic_tray_customer_sync` e
`tray_sync_scan_watermark` devem estar aplicadas antes da execução.

`POST /api/conversas/cliente` recebe `{"customerId":"UUID"}` e abre o contato
na Central. A empresa e o atendente vêm da sessão autenticada. Conversas existentes
são reutilizadas, sem tomar o atendimento de outro usuário; novos contatos ficam
atribuídos ao atendente e com o bot pausado. Abrir o contato não envia mensagem.
