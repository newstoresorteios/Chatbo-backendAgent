import httpx
import logging
import time

from app.config.settings import OPENAI_API_KEY, OPENAI_MODEL
from app.services.agent_knowledge import SUGGESTION_BEHAVIOR

logger = logging.getLogger(__name__)

COPILOT_SYSTEM = """
Voce e o Copiloto IA Elite do PulseDesk — consultor comercial e de suporte senior com raciocinio analitico.
O atendente humano usa sua resposta para resolver qualquer duvida do cliente sem escalar.

Voce TEM acesso a dados reais abaixo: clientes, produtos, pedidos, conversas, metricas de venda e funil CRM.
PRIORIDADE ABSOLUTA: cite numeros exatos do contexto (valores R$, quantidades, numeros de pedido, status, estoque).
Nunca responda de forma generica se o dado existir no contexto.

## Formato (sempre)
Diagnostico:
O que o atendente precisa saber ou fazer (1-2 frases objetivas).

Analise:
Resposta completa interpretando os dados — compare metricas, identifique gargalos, relacione pedido x cliente x produto.
Para follow-ups vagos ("me ajuda", "e agora?"): leia o historico e oriente o PROXIMO passo concreto.

Mensagem pronta:
Texto entre aspas, tom humano brasileiro, pronto para WhatsApp/e-mail.

Proximo passo:
Acao concreta com prazo (ex.: "em 30 min", "hoje ate 18h").

Alerta: (opcional — urgencia, estoque baixo, pedido atrasado)

## Regras
- Portugues do Brasil, profissional e natural — sem emojis, sem markdown, sem listas com bullet unicode
- NUNCA invente preco, estoque, prazo ou status — so use o contexto
- Pedidos Mercos = vendas reais sincronizadas; funil CRM = pipeline comercial (nao confundir)
- Se faltar dado: diga exatamente o que sincronizar (Mercos) ou perguntar ao cliente
- Para metricas: interprete (nao so repita numeros) — o que melhorar, onde esta o gargalo
"""

AGENT_SYSTEM = """
Voce e o Agente IA autonomo do PulseDesk (Robo de Atendimento).
Responda diretamente ao CLIENTE final — mensagem curta, cordial e util para WhatsApp.
Use dados reais do contexto (pedidos, produtos, estoque). Se faltar dado, peca ao cliente.
Faca triagem quando necessario: comercial, suporte, financeiro ou status de pedido.
Nao use markdown. Maximo 4 frases salvo se o cliente pedir detalhes.
"""

SUGGESTION_SYSTEM = f"""
Voce gera sugestoes para atendentes humanos.
{SUGGESTION_BEHAVIOR}
Retorne JSON valido: {{"insight":"...","suggestion":"mensagem pronta para o cliente","priority":"low|medium|high"}}
"""

MODE_SYSTEM = {
    "copilot": COPILOT_SYSTEM,
    "agent": AGENT_SYSTEM,
    "suggestion": SUGGESTION_SYSTEM,
}


def openai_configured() -> bool:
    key = OPENAI_API_KEY or ""
    return key.startswith("sk-")


def _parse_completion(data: dict, mode: str) -> str | None:
    choices = data.get("choices") or []
    if not choices:
        logger.warning("OpenAI retornou choices vazio (%s)", mode)
        return None
    message = choices[0].get("message") or {}
    content = message.get("content")
    return content.strip() if isinstance(content, str) and content.strip() else None


def call_openai(
    user_message: str,
    system_context: str,
    history: list[dict] | None = None,
    mode: str = "copilot",
    *,
    max_context_chars: int = 90000,
    history_limit: int = 20,
) -> str | None:
    if not openai_configured():
        return None

    system_prompt = MODE_SYSTEM.get(mode, COPILOT_SYSTEM)
    context_slice = system_context[:max_context_chars]

    messages: list[dict] = [
        {
            "role": "system",
            "content": f"{system_prompt}\n\n---\n\n# CONTEXTO EM TEMPO REAL\n\n{context_slice}",
        },
    ]

    for item in (history or [])[-history_limit:]:
        role = item.get("role", "user")
        if role not in ("user", "assistant"):
            role = "user"
        content = item.get("content", "")
        if content:
            messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": user_message})

    payload: dict = {
        "model": OPENAI_MODEL,
        "temperature": 0.45 if mode == "copilot" else 0.5,
        "max_tokens": 3500,
        "messages": messages,
    }

    if mode == "suggestion":
        payload["response_format"] = {"type": "json_object"}
        payload["temperature"] = 0.25

    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            response = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=120.0,
            )
            response.raise_for_status()
            result = _parse_completion(response.json(), mode)
            if result:
                return result
        except Exception as exc:
            last_exc = exc
            logger.warning("OpenAI falhou (%s) tentativa %s: %s", mode, attempt + 1, exc)
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))

    if last_exc:
        logger.warning("OpenAI esgotou tentativas (%s): %s", mode, last_exc)
    return None


def call_openai_resilient(
    user_message: str,
    system_context: str,
    history: list[dict] | None = None,
    mode: str = "copilot",
) -> str | None:
    reply = call_openai(user_message, system_context, history, mode)
    if reply:
        return reply

    if len(system_context) > 45000:
        logger.info("OpenAI retry Copiloto com contexto compacto")
        return call_openai(
            user_message,
            system_context,
            history,
            mode,
            max_context_chars=45000,
            history_limit=10,
        )
    return None
