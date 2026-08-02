import json
import logging
import re
import uuid

from app.config.settings import COPILOT_GPT_ONLY, OPENAI_MODEL
from app.services.agent_context_builder import AgentContextBuilder
from app.services.agent_intelligent_engine import generate_reply, generate_suggestion
from app.services.conversas_service import ConversasService
from app.services.openai_provider import call_openai_resilient, openai_configured

logger = logging.getLogger(__name__)


class AgentService:
    def __init__(self):
        self.context_builder = AgentContextBuilder()
        self.conversas = ConversasService()

    def _model_label(self) -> str:
        if openai_configured():
            suffix = " (100% GPT)" if COPILOT_GPT_ONLY else " + fallback local"
            return f"OpenAI {OPENAI_MODEL}{suffix}"
        return "Modo local (regex + dados Supabase)"

    def status(self) -> dict:
        try:
            total = len(self.conversas.listar_conversas())
        except Exception:
            total = 0
        gpt = openai_configured()
        return {
            "online": True,
            "model": self._model_label(),
            "avgResponseTime": "3s" if gpt else "1.2s",
            "questionsAnswered": total,
            "openaiEnabled": gpt,
            "gptOnly": gpt and COPILOT_GPT_ONLY,
            "intelligenceMode": "gpt" if gpt else "local",
        }

    def _gpt_unavailable_reply(self) -> str:
        return (
            "Diagnostico:\n"
            "O Copiloto GPT esta temporariamente indisponivel (OpenAI nao respondeu).\n\n"
            "Analise:\n"
            "A chave OPENAI_API_KEY esta configurada, mas a API falhou apos varias tentativas. "
            "Isso pode ser instabilidade da OpenAI, limite de uso ou timeout.\n\n"
            "Proximo passo:\n"
            "Aguarde 1 minuto e tente novamente. Se persistir, verifique OPENAI_API_KEY e creditos "
            "no painel OpenAI (Render → Environment)."
        )

    def _call_gpt(self, message: str, ctx: dict, history: list[dict] | None, mode: str) -> str | None:
        system_prompt = self.context_builder.to_prompt(ctx)
        return call_openai_resilient(message, system_prompt, history, mode)

    def build_context(
        self,
        conversation_id: str | None = None,
        customer_id: str | None = None,
        history: list[dict] | None = None,
        user_message: str | None = None,
    ) -> dict:
        return self.context_builder.build(conversation_id, customer_id, history, user_message)

    def _minimal_context(self, message: str) -> dict:
        products: list[dict] = []
        try:
            from app.services.pulsedesk_adapter import listar_produtos
            products = listar_produtos(page=1, page_size=40).get("data") or []
        except Exception:
            products = []
        return {
            "userMessage": message,
            "salesMetrics": self.context_builder._load_sales_metrics(),
            "platformStats": self.context_builder._platform_stats(),
            "recentOrders": self.context_builder._load_recent_orders(),
            "products": products,
            "productsCatalog": self.context_builder._format_catalog(products),
            "messages": [],
            "sessionHistory": [],
            "conversationMessages": [],
            "orders": [],
            "relatedOrders": [],
        }

    def chat(
        self,
        message: str,
        conversation_id: str | None = None,
        customer_id: str | None = None,
        mode: str = "copilot",
        history: list[dict] | None = None,
    ) -> dict:
        mode = mode or "copilot"
        conv_id = conversation_id or f"conv-{uuid.uuid4().hex[:8]}"

        try:
            ctx = self.context_builder.build(conversation_id, customer_id, history, message)
        except Exception as exc:
            logger.exception("Erro ao montar contexto do Copiloto: %s", exc)
            ctx = self._minimal_context(message)

        if openai_configured():
            try:
                ai_reply = self._call_gpt(message, ctx, history, mode)
                if ai_reply:
                    return {
                        "reply": ai_reply,
                        "conversationId": conv_id,
                        "source": "openai",
                    }
                if COPILOT_GPT_ONLY:
                    return {
                        "reply": self._gpt_unavailable_reply(),
                        "conversationId": conv_id,
                        "source": "openai",
                    }
            except Exception as exc:
                logger.warning("OpenAI no Copiloto falhou: %s", exc)
                if COPILOT_GPT_ONLY:
                    return {
                        "reply": self._gpt_unavailable_reply(),
                        "conversationId": conv_id,
                        "source": "openai",
                    }

        try:
            reply = generate_reply(message, ctx, mode)
            return {
                "reply": reply,
                "conversationId": conv_id,
                "source": "intelligent",
            }
        except Exception as exc:
            logger.exception("Erro no Copiloto chat: %s", exc)
            return {
                "reply": (
                    "Diagnostico:\n"
                    "Encontrei um erro ao processar sua pergunta.\n\n"
                    "Proximo passo:\n"
                    "Verifique sync Mercos/Supabase e tente de novo. "
                    f"Detalhe tecnico: {str(exc)[:80]}"
                ),
                "conversationId": conv_id,
                "source": "intelligent",
            }

    def suggest(
        self,
        conversation_id: str,
        customer_id: str | None = None,
    ) -> dict:
        try:
            ctx = self.context_builder.build(conversation_id, customer_id)
            if ctx.get("lastCustomerMessage"):
                ctx = self.context_builder.build(
                    conversation_id,
                    customer_id,
                    user_message=ctx.get("lastCustomerMessage"),
                )
            system_prompt = self.context_builder.to_prompt(ctx)

            prompt = (
                "Analise a conversa e gere JSON com insight, suggestion (mensagem pronta para o cliente) "
                'e priority (low|medium|high).\n\n'
                f'Última mensagem do cliente: {ctx.get("lastCustomerMessage") or ""}'
            )

            raw = call_openai_resilient(prompt, system_prompt, [], "suggestion")
            if raw:
                match = re.search(r"\{[\s\S]*\}", raw)
                if match:
                    try:
                        parsed = json.loads(match.group(0))
                        return {
                            "insight": parsed.get("insight", ""),
                            "suggestion": parsed.get("suggestion", ""),
                            "priority": parsed.get("priority", "medium"),
                            "source": "openai",
                        }
                    except json.JSONDecodeError:
                        pass

            if openai_configured() and COPILOT_GPT_ONLY:
                return {
                    "insight": "GPT indisponivel — tente novamente em instantes.",
                    "suggestion": "Ola! Recebemos sua mensagem e retornaremos em breve.",
                    "priority": "medium",
                    "source": "openai",
                }

            suggestion = generate_suggestion(ctx)
            return {**suggestion, "source": "intelligent"}
        except Exception as exc:
            logger.exception("Erro no Copiloto suggest: %s", exc)
            return {
                "insight": "Copiloto indisponível momentaneamente.",
                "suggestion": "Olá! Recebemos sua mensagem e retornaremos em breve.",
                "priority": "medium",
                "source": "intelligent",
            }


agent_service = AgentService()
