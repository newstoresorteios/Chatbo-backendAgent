# Checklist — smoke test de integração

O script principal vive no repositório **NSAgentForSorteios**:

```bash
cd ../NSAgentForSorteios
export CHATBO_BASE_URL=https://seu-chatbo.onrender.com   # URL deste serviço
export NSAGENT_BASE_URL=...
export TRAY_ADAPTER_URL=...
export TRAY_ADAPTER_TOKEN=...
python scripts/integration_smoke_test.py
```

Documentação completa: `NSAgentForSorteios/docs/integration_smoke_test.md`.

## O que este serviço (Chatbo) expõe

| Check | Endpoint | Esperado |
|-------|----------|----------|
| Health | `GET /health` | `status: "ok"` (não `degraded`) |

Variáveis mínimas para health saudável (ver `.env.example`):

- `SUPABASE_URL` — URL HTTPS do projeto
- `SUPABASE_KEY` — **service_role** (não anon)
- `JWT_SECRET`

## TRAYadaptor no Chatbo

Diferente do NSAgent, URL e token do TRAYadaptor no Chatbo ficam na **integração por workspace** (Supabase), não em env global. Ao validar produção:

1. Confirme no painel/admin que o workspace usa a mesma base URL do `TRAY_ADAPTER_URL` do NSAgent.
2. O token interno deve coincidir com `TRAY_ADAPTER_TOKEN` configurado no TRAYadaptor.
3. Rode o smoke test do NSAgent — o check `TRAYadaptor /health/tray` valida OAuth/cache Tray.

## Teste rápido só do Chatbo

```bash
curl -s "$CHATBO_BASE_URL/health" | python -m json.tool
```
